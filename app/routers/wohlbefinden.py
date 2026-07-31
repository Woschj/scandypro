import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import select

from app.core.access import hat_wohlbefinden_freigabe, require_owner
from app.core.audit import protokolliere
from app.core.deps import CurrentUser, SessionDep
from app.core.templating import templates
from app.models.audit import AuditAktion, AuditZieltyp
from app.models.organisation import PsmZuordnung
from app.models.user import RoleEnum, User
from app.models.wohlbefinden import WohlbefindenEintrag, WohlbefindenFreigabe, WohlbefindenFreigabeUmfang

router = APIRouter(prefix="/wohlbefinden", tags=["wohlbefinden"])

WOCHENTAG_NAMEN = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _wochenstart(bezugsdatum: date) -> date:
    return bezugsdatum - timedelta(days=bezugsdatum.weekday())


def _mittelwert(eintraege: list[WohlbefindenEintrag], feld: str) -> float | None:
    werte = [getattr(e, feld) for e in eintraege]
    return round(sum(werte) / len(werte), 1) if werte else None


def _monats_chart(eintraege: list[WohlbefindenEintrag], monat_start: date, tage_gesamt: int) -> dict:
    breite, hoehe = 640, 120
    if not eintraege:
        return {"hat_daten": False, "breite": breite, "hoehe": hoehe}

    def x_fuer(d: date) -> float:
        return (d - monat_start).days / max(tage_gesamt - 1, 1) * breite

    def y_fuer(wert: float) -> float:
        return hoehe - 10 - (wert - 1) / 4 * (hoehe - 20)

    stimmung_punkte = " ".join(f"{x_fuer(e.datum):.1f},{y_fuer(e.stimmung):.1f}" for e in eintraege)
    belastbarkeit_punkte = " ".join(f"{x_fuer(e.datum):.1f},{y_fuer(e.belastbarkeit):.1f}" for e in eintraege)
    return {
        "hat_daten": True,
        "breite": breite,
        "hoehe": hoehe,
        "stimmung_punkte": stimmung_punkte,
        "belastbarkeit_punkte": belastbarkeit_punkte,
    }


async def _wochenansicht_kontext(session: SessionDep, teilnehmer_id: int, woche_start: str | None) -> dict:
    """Baut den kompletten Render-Kontext einer Wochenansicht - gemeinsam
    genutzt von der eigenen Ansicht (Teilnehmer:in, mit Drag-Interaktion)
    und der PSM-Ansicht (rein lesend, nur bei aktiver Freigabe)."""
    if woche_start:
        try:
            start = _wochenstart(date.fromisoformat(woche_start))
        except ValueError:
            start = _wochenstart(date.today())
    else:
        start = _wochenstart(date.today())

    tage_der_woche = [start + timedelta(days=i) for i in range(7)]
    result = await session.execute(
        select(WohlbefindenEintrag).where(
            WohlbefindenEintrag.teilnehmer_id == teilnehmer_id,
            WohlbefindenEintrag.datum.in_(tage_der_woche),
        )
    )
    eintraege_by_datum = {e.datum: e for e in result.scalars().all()}

    wochendaten = []
    for i, tag in enumerate(tage_der_woche):
        eintrag = eintraege_by_datum.get(tag)
        wochendaten.append(
            {
                "datum": tag.isoformat(),
                "label": f"{WOCHENTAG_NAMEN[i]} {tag.strftime('%d.%m.')}",
                "stimmung": eintrag.stimmung if eintrag else 3.0,
                "belastbarkeit": eintrag.belastbarkeit if eintrag else 3.0,
                "kommentar": eintrag.kommentar if eintrag else None,
                "gesetzt": eintrag is not None,
            }
        )

    vorwoche_tage = [start - timedelta(days=7) + timedelta(days=i) for i in range(7)]
    vorwoche_result = await session.execute(
        select(WohlbefindenEintrag).where(
            WohlbefindenEintrag.teilnehmer_id == teilnehmer_id,
            WohlbefindenEintrag.datum.in_(vorwoche_tage),
        )
    )
    diese_woche_eintraege = list(eintraege_by_datum.values())
    vorwoche_eintraege = list(vorwoche_result.scalars().all())

    auswertung = {
        "stimmung_avg": _mittelwert(diese_woche_eintraege, "stimmung"),
        "belastbarkeit_avg": _mittelwert(diese_woche_eintraege, "belastbarkeit"),
        "stimmung_avg_vorwoche": _mittelwert(vorwoche_eintraege, "stimmung"),
        "belastbarkeit_avg_vorwoche": _mittelwert(vorwoche_eintraege, "belastbarkeit"),
    }

    monat_tage_gesamt = 30
    monat_start = date.today() - timedelta(days=monat_tage_gesamt - 1)
    monat_result = await session.execute(
        select(WohlbefindenEintrag)
        .where(WohlbefindenEintrag.teilnehmer_id == teilnehmer_id, WohlbefindenEintrag.datum >= monat_start)
        .order_by(WohlbefindenEintrag.datum)
    )
    monat_chart = _monats_chart(list(monat_result.scalars().all()), monat_start, monat_tage_gesamt)

    wochendaten_json = json.dumps(wochendaten).replace("</", "<\\/")

    return {
        "wochendaten": wochendaten,
        "wochendaten_json": wochendaten_json,
        "woche_start": start.isoformat(),
        "vorherige_woche": (start - timedelta(days=7)).isoformat(),
        "naechste_woche": (start + timedelta(days=7)).isoformat(),
        "ist_aktuelle_woche": start == _wochenstart(date.today()),
        "wochenbereich": f"{start.strftime('%d.%m.')} – {(start + timedelta(days=6)).strftime('%d.%m.%Y')}",
        "auswertung": auswertung,
        "monat_chart": monat_chart,
        "monat_start": monat_start.strftime("%d.%m."),
        "monat_ende": date.today().strftime("%d.%m."),
    }


@router.get("", response_class=HTMLResponse)
async def uebersicht(
    request: Request, current_user: CurrentUser, session: SessionDep, woche_start: str | None = None
):
    if current_user.role != RoleEnum.teilnehmer:
        return templates.TemplateResponse(
            request, "wohlbefinden/kein_zugriff.html", {"current_user": current_user}, status_code=403
        )

    kontext = await _wochenansicht_kontext(session, current_user.id, woche_start)

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
            "freigaben": freigaben,
            "psm_kontakt": psm_kontakt,
            **kontext,
        },
    )


@router.get("/teilnehmer/{teilnehmer_id}", response_class=HTMLResponse)
async def teilnehmer_ansicht(
    request: Request,
    teilnehmer_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    woche_start: str | None = None,
):
    """Rein lesende Ansicht für psychosoziale Mitarbeit - erfordert sowohl
    eine organisatorische PsmZuordnung als auch eine aktive, von der/dem
    Teilnehmer:in selbst erteilte Freigabe. Jeder Aufruf wird protokolliert
    (siehe app/core/audit.py)."""
    if current_user.role != RoleEnum.psychosoziale_mitarbeit:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur psychosoziale Mitarbeit nutzt diese Ansicht.")

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

    kontext = await _wochenansicht_kontext(session, teilnehmer_id, woche_start)

    return templates.TemplateResponse(
        request,
        "wohlbefinden/teilnehmer_ansicht.html",
        {
            "current_user": current_user,
            "teilnehmer": teilnehmer,
            **kontext,
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


class TagWertePayload(BaseModel):
    datum: date
    stimmung: float = PydanticField(ge=1.0, le=5.0)
    belastbarkeit: float = PydanticField(ge=1.0, le=5.0)


class TagKommentarPayload(BaseModel):
    datum: date
    kommentar: str


class TagLoeschenPayload(BaseModel):
    datum: date


async def _hole_oder_erstelle(session: SessionDep, current_user, datum: date) -> WohlbefindenEintrag:
    result = await session.execute(
        select(WohlbefindenEintrag).where(
            WohlbefindenEintrag.teilnehmer_id == current_user.id, WohlbefindenEintrag.datum == datum
        )
    )
    eintrag = result.scalar_one_or_none()
    if eintrag is None:
        eintrag = WohlbefindenEintrag(
            teilnehmer_id=current_user.id, datum=datum, stimmung=3.0, belastbarkeit=3.0
        )
    return eintrag


@router.post("/tag")
async def tag_speichern(payload: TagWertePayload, current_user: CurrentUser, session: SessionDep):
    if current_user.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    eintrag = await _hole_oder_erstelle(session, current_user, payload.datum)
    eintrag.stimmung = payload.stimmung
    eintrag.belastbarkeit = payload.belastbarkeit
    eintrag.aktualisiert_am = datetime.utcnow()
    session.add(eintrag)
    await session.commit()
    return {"ok": True}


@router.post("/tag/kommentar")
async def kommentar_speichern(payload: TagKommentarPayload, current_user: CurrentUser, session: SessionDep):
    if current_user.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    eintrag = await _hole_oder_erstelle(session, current_user, payload.datum)
    eintrag.kommentar = payload.kommentar or None
    eintrag.aktualisiert_am = datetime.utcnow()
    session.add(eintrag)
    await session.commit()
    return {"ok": True}


@router.post("/tag/loeschen")
async def tag_loeschen(payload: TagLoeschenPayload, current_user: CurrentUser, session: SessionDep):
    result = await session.execute(
        select(WohlbefindenEintrag).where(
            WohlbefindenEintrag.teilnehmer_id == current_user.id, WohlbefindenEintrag.datum == payload.datum
        )
    )
    eintrag = result.scalar_one_or_none()
    if eintrag is None:
        return {"ok": True}
    require_owner(current_user, eintrag.teilnehmer_id, "Kein Zugriff auf diesen Eintrag.")
    await session.delete(eintrag)
    await session.commit()
    return {"ok": True}
