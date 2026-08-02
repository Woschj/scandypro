from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select

from app.core.access import hat_wohlbefinden_freigabe, require_owner
from app.core.audit import protokolliere
from app.core.deps import CurrentUser, SessionDep, verify_csrf
from app.core.tagebuch_prompts import abend_impuls_des_tages, morgen_impuls_des_tages
from app.core.templating import templates
from app.models.audit import AuditAktion, AuditZieltyp
from app.models.organisation import PsmZuordnung
from app.models.user import RoleEnum, User
from app.models.wohlbefinden import TagebuchEintrag, WohlbefindenFreigabe, WohlbefindenFreigabeUmfang

router = APIRouter(prefix="/wohlbefinden", tags=["wohlbefinden"], dependencies=[Depends(verify_csrf)])

WOCHENTAG_NAMEN = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
VERLAUF_TAGE_ANZAHL = 14


def _tag_label(d: date) -> str:
    return f"{WOCHENTAG_NAMEN[d.weekday()]}, {d.strftime('%d.%m.%Y')}"


async def _hole_eintrag(session: SessionDep, teilnehmer_id: int, datum: date) -> TagebuchEintrag | None:
    result = await session.execute(
        select(TagebuchEintrag).where(
            TagebuchEintrag.teilnehmer_id == teilnehmer_id, TagebuchEintrag.datum == datum
        )
    )
    return result.scalar_one_or_none()


async def _hole_oder_erstelle(session: SessionDep, teilnehmer_id: int, datum: date) -> TagebuchEintrag:
    eintrag = await _hole_eintrag(session, teilnehmer_id, datum)
    if eintrag is None:
        eintrag = TagebuchEintrag(teilnehmer_id=teilnehmer_id, datum=datum)
    return eintrag


def _eintrag_anzeige(eintrag: TagebuchEintrag | None, datum: date) -> dict:
    """Einheitliche Anzeige-Struktur für einen Tag - auch wenn noch kein
    Eintrag existiert (dann mit heutigen/aktuellen Impuls-Vorschau-Fragen,
    aber ohne Antworten), damit das Template nicht zwischen "gibt es schon"
    und "gibt es noch nicht" unterscheiden muss."""
    if eintrag is None:
        return {
            "datum": datum,
            "label": _tag_label(datum),
            "dankbarkeit": ["", "", ""],
            "morgen_impuls_frage": None,
            "morgen_impuls_antwort": "",
            "morgen_erledigt": False,
            "highlights": ["", "", ""],
            "abend_impuls_frage": None,
            "abend_impuls_antwort": "",
            "abend_erledigt": False,
        }
    return {
        "datum": eintrag.datum,
        "label": _tag_label(eintrag.datum),
        "dankbarkeit": [eintrag.dankbarkeit_1 or "", eintrag.dankbarkeit_2 or "", eintrag.dankbarkeit_3 or ""],
        "morgen_impuls_frage": eintrag.morgen_impuls_frage,
        "morgen_impuls_antwort": eintrag.morgen_impuls_antwort or "",
        "morgen_erledigt": eintrag.morgen_ausgefuellt_am is not None,
        "highlights": [eintrag.highlight_1 or "", eintrag.highlight_2 or "", eintrag.highlight_3 or ""],
        "abend_impuls_frage": eintrag.abend_impuls_frage,
        "abend_impuls_antwort": eintrag.abend_impuls_antwort or "",
        "abend_erledigt": eintrag.abend_ausgefuellt_am is not None,
    }


def _hat_inhalt(anzeige: dict) -> bool:
    return (
        any(anzeige["dankbarkeit"])
        or anzeige["morgen_impuls_antwort"]
        or any(anzeige["highlights"])
        or anzeige["abend_impuls_antwort"]
    )


async def _verlauf(session: SessionDep, teilnehmer_id: int, bis_datum: date) -> list[dict]:
    """Liste der letzten VERLAUF_TAGE_ANZAHL Tage mit Inhalt, neueste zuerst -
    ersetzt die frühere Mood-Heatmap (siehe CHANGELOG). Bewusst als lesbare
    Liste statt Farbraster: Freitext lässt sich nicht sinnvoll auf eine
    Farbskala reduzieren, ohne genau die Bewertungs-Optik zu erzeugen, die
    das Tagebuch-Format vermeiden soll."""
    start = bis_datum - timedelta(days=VERLAUF_TAGE_ANZAHL - 1)
    result = await session.execute(
        select(TagebuchEintrag)
        .where(
            TagebuchEintrag.teilnehmer_id == teilnehmer_id,
            TagebuchEintrag.datum >= start,
            TagebuchEintrag.datum <= bis_datum,
        )
        .order_by(TagebuchEintrag.datum.desc())
    )
    eintraege = result.scalars().all()
    anzeigen = [_eintrag_anzeige(e, e.datum) for e in eintraege]
    return [a for a in anzeigen if _hat_inhalt(a)]


@router.get("", response_class=HTMLResponse)
async def uebersicht(request: Request, current_user: CurrentUser, session: SessionDep, tag: str | None = None):
    if current_user.role != RoleEnum.teilnehmer:
        return templates.TemplateResponse(
            request, "wohlbefinden/kein_zugriff.html", {"current_user": current_user}, status_code=403
        )

    heute = date.today()
    try:
        ausgewaehlter_tag = min(date.fromisoformat(tag), heute) if tag else heute
    except ValueError:
        ausgewaehlter_tag = heute

    eintrag = await _hole_eintrag(session, current_user.id, ausgewaehlter_tag)
    anzeige = _eintrag_anzeige(eintrag, ausgewaehlter_tag)
    if anzeige["morgen_impuls_frage"] is None:
        anzeige["morgen_impuls_frage"] = morgen_impuls_des_tages(current_user.id, ausgewaehlter_tag)
    if anzeige["abend_impuls_frage"] is None:
        anzeige["abend_impuls_frage"] = abend_impuls_des_tages(current_user.id, ausgewaehlter_tag)

    verlauf = await _verlauf(session, current_user.id, heute)

    freigaben_result = await session.execute(
        select(WohlbefindenFreigabe)
        .where(WohlbefindenFreigabe.teilnehmer_id == current_user.id, WohlbefindenFreigabe.widerrufen_am.is_(None))
        .order_by(WohlbefindenFreigabe.erstellt_am.desc())
    )
    freigaben = list(freigaben_result.scalars().all())

    psm_result = await session.execute(
        select(PsmZuordnung).where(PsmZuordnung.teilnehmer_id == current_user.id)
    )
    psm_zuordnung = psm_result.scalar_one_or_none()
    psm_kontakt = await session.get(User, psm_zuordnung.psm_id) if psm_zuordnung else None

    return templates.TemplateResponse(
        request,
        "wohlbefinden/uebersicht.html",
        {
            "current_user": current_user,
            "tag": anzeige,
            "ist_heute": ausgewaehlter_tag == heute,
            "vorheriger_tag": (ausgewaehlter_tag - timedelta(days=1)).isoformat(),
            "naechster_tag": (ausgewaehlter_tag + timedelta(days=1)).isoformat() if ausgewaehlter_tag < heute else None,
            "verlauf": verlauf,
            "freigaben": freigaben,
            "psm_kontakt": psm_kontakt,
        },
    )


@router.get("/teilnehmer/{teilnehmer_id}", response_class=HTMLResponse)
async def teilnehmer_ansicht(
    request: Request,
    teilnehmer_id: int,
    current_user: CurrentUser,
    session: SessionDep,
):
    """Rein lesende Ansicht für psychosoziale Mitarbeiter:innen - erfordert sowohl
    eine organisatorische PsmZuordnung als auch eine aktive, von der/dem
    Teilnehmer:in selbst erteilte Freigabe. Jeder Aufruf wird protokolliert
    (siehe app/core/audit.py)."""
    if current_user.role != RoleEnum.psychosoziale_mitarbeit:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur psychosoziale Mitarbeiter:innen nutzen diese Ansicht.")

    zuordnung_result = await session.execute(
        select(PsmZuordnung).where(
            PsmZuordnung.psm_id == current_user.id, PsmZuordnung.teilnehmer_id == teilnehmer_id
        )
    )
    if zuordnung_result.first() is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Diese Person ist dir nicht zugeordnet.")

    if not await hat_wohlbefinden_freigabe(session, current_user.id, teilnehmer_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Keine aktive Freigabe für diese Person.")

    teilnehmer = await session.get(User, teilnehmer_id)
    if teilnehmer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    await protokolliere(
        session,
        akteur_id=current_user.id,
        aktion=AuditAktion.wohlbefinden_gelesen,
        zieltyp=AuditZieltyp.wohlbefinden,
        ziel_teilnehmer_id=teilnehmer_id,
    )

    verlauf = await _verlauf(session, teilnehmer_id, date.today())

    return templates.TemplateResponse(
        request,
        "wohlbefinden/teilnehmer_ansicht.html",
        {
            "current_user": current_user,
            "teilnehmer": teilnehmer,
            "verlauf": verlauf,
        },
    )


@router.post("/freigaben")
async def freigabe_erstellen(
    current_user: CurrentUser,
    session: SessionDep,
    empfaenger_id: int = Form(...),
    umfang: WohlbefindenFreigabeUmfang = Form(WohlbefindenFreigabeUmfang.alle),
    gueltig_bis: str = Form(""),
):
    if current_user.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    empfaenger = await session.get(User, empfaenger_id)
    if empfaenger is None or empfaenger.role != RoleEnum.psychosoziale_mitarbeit:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Empfänger:in.")

    session.add(
        WohlbefindenFreigabe(
            teilnehmer_id=current_user.id,
            empfaenger_id=empfaenger_id,
            umfang=umfang,
            gueltig_bis=date.fromisoformat(gueltig_bis) if gueltig_bis else None,
        )
    )
    await session.commit()
    return RedirectResponse(url="/wohlbefinden", status_code=303)


@router.post("/freigaben/{freigabe_id}/widerrufen")
async def freigabe_widerrufen(freigabe_id: int, current_user: CurrentUser, session: SessionDep):
    freigabe = await session.get(WohlbefindenFreigabe, freigabe_id)
    if freigabe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, freigabe.teilnehmer_id, "Kein Zugriff auf diese Freigabe.")

    freigabe.widerrufen_am = datetime.utcnow()
    session.add(freigabe)
    await session.commit()
    return RedirectResponse(url="/wohlbefinden", status_code=303)


@router.post("/morgen")
async def morgen_speichern(
    current_user: CurrentUser,
    session: SessionDep,
    datum: str = Form(...),
    dankbarkeit_1: str = Form(""),
    dankbarkeit_2: str = Form(""),
    dankbarkeit_3: str = Form(""),
    morgen_impuls_frage: str = Form(""),
    morgen_impuls_antwort: str = Form(""),
):
    if current_user.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    tag_datum = date.fromisoformat(datum)
    eintrag = await _hole_oder_erstelle(session, current_user.id, tag_datum)
    eintrag.dankbarkeit_1 = dankbarkeit_1 or None
    eintrag.dankbarkeit_2 = dankbarkeit_2 or None
    eintrag.dankbarkeit_3 = dankbarkeit_3 or None
    eintrag.morgen_impuls_frage = morgen_impuls_frage or morgen_impuls_des_tages(current_user.id, tag_datum)
    eintrag.morgen_impuls_antwort = morgen_impuls_antwort or None
    eintrag.morgen_ausgefuellt_am = datetime.utcnow()
    session.add(eintrag)
    await session.commit()
    return RedirectResponse(url=f"/wohlbefinden?tag={datum}", status_code=303)


@router.post("/abend")
async def abend_speichern(
    current_user: CurrentUser,
    session: SessionDep,
    datum: str = Form(...),
    highlight_1: str = Form(""),
    highlight_2: str = Form(""),
    highlight_3: str = Form(""),
    abend_impuls_frage: str = Form(""),
    abend_impuls_antwort: str = Form(""),
):
    if current_user.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    tag_datum = date.fromisoformat(datum)
    eintrag = await _hole_oder_erstelle(session, current_user.id, tag_datum)
    eintrag.highlight_1 = highlight_1 or None
    eintrag.highlight_2 = highlight_2 or None
    eintrag.highlight_3 = highlight_3 or None
    eintrag.abend_impuls_frage = abend_impuls_frage or abend_impuls_des_tages(current_user.id, tag_datum)
    eintrag.abend_impuls_antwort = abend_impuls_antwort or None
    eintrag.abend_ausgefuellt_am = datetime.utcnow()
    session.add(eintrag)
    await session.commit()
    return RedirectResponse(url=f"/wohlbefinden?tag={datum}", status_code=303)


@router.post("/tag/loeschen")
async def tag_loeschen(current_user: CurrentUser, session: SessionDep, datum: str = Form(...)):
    tag_datum = date.fromisoformat(datum)
    eintrag = await _hole_eintrag(session, current_user.id, tag_datum)
    if eintrag is not None:
        require_owner(current_user, eintrag.teilnehmer_id, "Kein Zugriff auf diesen Eintrag.")
        await session.delete(eintrag)
        await session.commit()
    return RedirectResponse(url=f"/wohlbefinden?tag={datum}", status_code=303)
