import base64
import binascii
import io
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlmodel import select

from app.core.access import hat_wohlbefinden_freigabe, require_owner, require_role
from app.core.atemuebungen import atemuebung_des_tages, atemuebung_punkte
from app.core.audit import protokolliere
from app.core.deps import CurrentUser, SessionDep, verify_csrf
from app.core.tagebuch_prompts import abend_impuls_des_tages, morgen_impuls_des_tages
from app.core.tagesuebungen import (
    WORT_DES_TAGES_OPTIONEN,
    abenduebung_des_tages,
    koerperscan_zonen,
    morgenuebung_des_tages,
    staerken_karte_des_tages,
)
from app.core.templating import templates
from app.core.uploads import datei_lesen_entschluesselt, datei_loeschen, datei_speichern
from app.models.audit import AuditAktion, AuditZieltyp
from app.models.organisation import Abteilung, PsmZuordnung
from app.models.user import RoleEnum, User
from app.models.wohlbefinden import (
    TagebuchEintrag,
    Unterstuetzungsanfrage,
    WohlbefindenFreigabe,
    WohlbefindenFreigabeUmfang,
)

router = APIRouter(prefix="/wohlbefinden", tags=["wohlbefinden"], dependencies=[Depends(verify_csrf)])

WOCHENTAG_NAMEN = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
VERLAUF_TAGE_ANZAHL = 14
ENERGIE_LEVEL_MIN = 1
ENERGIE_LEVEL_MAX = 4


async def _zeichnung_speichern(teilnehmer_id: int, daten_url: str) -> str:
    """Speichert eine im Browser gezeichnete PNG-Skizze (Canvas
    `toDataURL()`-String) genauso verschlüsselt wie Bewerbungsunterlagen
    (siehe app/core/uploads.py) - auf der Platte liegt nie Klartext-
    Bilddaten. Wirft HTTPException bei kaputten/zu großen Daten (dieselbe
    Größenprüfung wie bei normalen Datei-Uploads)."""
    try:
        _, _, b64 = daten_url.partition(",")
        rohdaten = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Zeichnung konnte nicht gelesen werden.") from exc

    upload = UploadFile(filename="zeichnung.png", file=io.BytesIO(rohdaten))
    _, speicherpfad, _ = await datei_speichern(upload, f"tagebuch/{teilnehmer_id}")
    return speicherpfad


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
            "eintrag_id": None,
            "datum": datum,
            "label": _tag_label(datum),
            "dankbarkeit": ["", "", ""],
            "morgen_impuls_frage": None,
            "morgen_impuls_antwort": "",
            "morgen_erledigt": False,
            "energie_level": None,
            "morgen_uebung_typ": None,
            "atemuebung_name": None,
            "atemuebung_erledigt": False,
            "koerperscan_erledigt": False,
            "grounding_erledigt": False,
            "wort_des_tages": "",
            "staerken_karte_frage": None,
            "staerken_karte_antwort": "",
            "staerken_karte_erledigt": False,
            "highlights": ["", "", ""],
            "abend_impuls_frage": None,
            "abend_impuls_antwort": "",
            "abend_erledigt": False,
            "abend_uebung_typ": None,
            "hat_zeichnung": False,
            "mandala_erledigt": False,
            "ruhe_ort_sehen": "",
            "ruhe_ort_hoeren": "",
            "ruhe_ort_spueren": "",
            "gedanke_belastend": "",
            "gedanke_ausgewogen": "",
            "sorgen_los_erledigt": False,
            "hat_dankbarkeitsfoto": False,
            "mini_ziel_text": "",
            "mini_ziel_geschafft": False,
            "check_pause_gemacht": False,
            "check_jemandem_geholfen": False,
            "check_kleines_erfolgserlebnis": False,
        }
    return {
        "eintrag_id": eintrag.id,
        "datum": eintrag.datum,
        "label": _tag_label(eintrag.datum),
        "dankbarkeit": [eintrag.dankbarkeit_1 or "", eintrag.dankbarkeit_2 or "", eintrag.dankbarkeit_3 or ""],
        "morgen_impuls_frage": eintrag.morgen_impuls_frage,
        "morgen_impuls_antwort": eintrag.morgen_impuls_antwort or "",
        "morgen_erledigt": eintrag.morgen_ausgefuellt_am is not None,
        "energie_level": eintrag.energie_level,
        "morgen_uebung_typ": eintrag.morgen_uebung_typ,
        "atemuebung_name": eintrag.atemuebung_name,
        "atemuebung_erledigt": eintrag.atemuebung_erledigt_am is not None,
        "koerperscan_erledigt": eintrag.koerperscan_erledigt_am is not None,
        "grounding_erledigt": eintrag.grounding_erledigt_am is not None,
        "wort_des_tages": eintrag.wort_des_tages or "",
        "staerken_karte_frage": eintrag.staerken_karte_frage,
        "staerken_karte_antwort": eintrag.staerken_karte_antwort or "",
        "staerken_karte_erledigt": eintrag.staerken_karte_erledigt_am is not None,
        "highlights": [eintrag.highlight_1 or "", eintrag.highlight_2 or "", eintrag.highlight_3 or ""],
        "abend_impuls_frage": eintrag.abend_impuls_frage,
        "abend_impuls_antwort": eintrag.abend_impuls_antwort or "",
        "abend_erledigt": eintrag.abend_ausgefuellt_am is not None,
        "abend_uebung_typ": eintrag.abend_uebung_typ,
        "hat_zeichnung": eintrag.zeichnung_pfad is not None,
        "mandala_erledigt": eintrag.mandala_erledigt_am is not None,
        "ruhe_ort_sehen": eintrag.ruhe_ort_sehen or "",
        "ruhe_ort_hoeren": eintrag.ruhe_ort_hoeren or "",
        "ruhe_ort_spueren": eintrag.ruhe_ort_spueren or "",
        "gedanke_belastend": eintrag.gedanke_belastend or "",
        "gedanke_ausgewogen": eintrag.gedanke_ausgewogen or "",
        "sorgen_los_erledigt": eintrag.sorgen_los_erledigt_am is not None,
        "hat_dankbarkeitsfoto": eintrag.dankbarkeitsfoto_pfad is not None,
        "mini_ziel_text": eintrag.mini_ziel_text or "",
        "mini_ziel_geschafft": eintrag.mini_ziel_geschafft,
        "check_pause_gemacht": eintrag.check_pause_gemacht,
        "check_jemandem_geholfen": eintrag.check_jemandem_geholfen,
        "check_kleines_erfolgserlebnis": eintrag.check_kleines_erfolgserlebnis,
    }


def _hat_inhalt(anzeige: dict) -> bool:
    return (
        any(anzeige["dankbarkeit"])
        or anzeige["morgen_impuls_antwort"]
        or anzeige["energie_level"] is not None
        or anzeige["atemuebung_erledigt"]
        or anzeige["koerperscan_erledigt"]
        or anzeige["grounding_erledigt"]
        or anzeige["wort_des_tages"]
        or anzeige["staerken_karte_erledigt"]
        or any(anzeige["highlights"])
        or anzeige["abend_impuls_antwort"]
        or anzeige["hat_zeichnung"]
        or anzeige["mandala_erledigt"]
        or anzeige["ruhe_ort_sehen"]
        or anzeige["gedanke_belastend"]
        or anzeige["sorgen_los_erledigt"]
        or anzeige["hat_dankbarkeitsfoto"]
        or anzeige["mini_ziel_text"]
        or anzeige["check_pause_gemacht"]
        or anzeige["check_jemandem_geholfen"]
        or anzeige["check_kleines_erfolgserlebnis"]
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
    if anzeige["atemuebung_name"] is None:
        anzeige["atemuebung_name"] = atemuebung_des_tages(current_user.id, ausgewaehlter_tag)
    anzeige["atemuebung_punkte"] = atemuebung_punkte(anzeige["atemuebung_name"])

    if anzeige["morgen_uebung_typ"] is None:
        anzeige["morgen_uebung_typ"] = morgenuebung_des_tages(current_user.id, ausgewaehlter_tag)
    if anzeige["staerken_karte_frage"] is None:
        anzeige["staerken_karte_frage"] = staerken_karte_des_tages(current_user.id, ausgewaehlter_tag)
    anzeige["koerperscan_zonen"] = koerperscan_zonen()

    if anzeige["abend_uebung_typ"] is None:
        anzeige["abend_uebung_typ"] = abenduebung_des_tages(current_user.id, ausgewaehlter_tag)

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

    # Weitere psychosoziale Mitarbeiter:innen derselben Abteilung als
    # zusätzliche Kontaktoption (siehe VB-002-Feedback) - unabhängig von der
    # organisatorischen PsmZuordnung, rein informativ, kein Datenzugriff.
    andere_psm: list[User] = []
    if current_user.abteilung_id is not None:
        andere_psm_result = await session.execute(
            select(User).where(
                User.role == RoleEnum.psychosoziale_mitarbeit,
                User.abteilung_id == current_user.abteilung_id,
                User.id != (psm_kontakt.id if psm_kontakt else -1),
            )
        )
        andere_psm = list(andere_psm_result.scalars().all())

    anfrage_offen = False
    if psm_kontakt is not None:
        offene_anfrage = await session.execute(
            select(Unterstuetzungsanfrage.id).where(
                Unterstuetzungsanfrage.teilnehmer_id == current_user.id,
                Unterstuetzungsanfrage.empfaenger_id == psm_kontakt.id,
                Unterstuetzungsanfrage.gesehen_am.is_(None),
            )
        )
        anfrage_offen = offene_anfrage.first() is not None

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
            "andere_psm": andere_psm,
            "wort_optionen": WORT_DES_TAGES_OPTIONEN,
            "anfrage_offen": anfrage_offen,
        },
    )


@router.post("/unterstuetzung-anfragen")
async def unterstuetzung_anfragen(current_user: CurrentUser, session: SessionDep):
    """Freiwillige, bewusste Aktion aus "Ich möchte jetzt Unterstützung" -
    komplett unabhängig von Tagebuch-Inhalten (siehe Modul-Docstring von
    Unterstuetzungsanfrage). Legt nur an, wenn noch keine unerledigte
    Anfrage an dieselbe PSM vorliegt, damit Mehrfach-Klicks nicht mehrere
    Einträge im PSM-Dashboard erzeugen."""
    require_role(current_user, RoleEnum.teilnehmer, "Nur Teilnehmer:innen können Unterstützung anfragen.")

    psm_result = await session.execute(select(PsmZuordnung).where(PsmZuordnung.teilnehmer_id == current_user.id))
    psm_zuordnung = psm_result.scalar_one_or_none()
    if psm_zuordnung is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dir ist noch keine psychosoziale Mitarbeiter:in zugeordnet.")

    bereits_offen = await session.execute(
        select(Unterstuetzungsanfrage.id).where(
            Unterstuetzungsanfrage.teilnehmer_id == current_user.id,
            Unterstuetzungsanfrage.empfaenger_id == psm_zuordnung.psm_id,
            Unterstuetzungsanfrage.gesehen_am.is_(None),
        )
    )
    if bereits_offen.first() is None:
        session.add(Unterstuetzungsanfrage(teilnehmer_id=current_user.id, empfaenger_id=psm_zuordnung.psm_id))
        await session.commit()
    return RedirectResponse(url="/wohlbefinden", status_code=303)


@router.post("/unterstuetzung-anfragen/{anfrage_id}/gesehen")
async def unterstuetzung_anfrage_gesehen(anfrage_id: int, current_user: CurrentUser, session: SessionDep):
    require_role(current_user, RoleEnum.psychosoziale_mitarbeit, "Nur psychosoziale Mitarbeiter:innen bearbeiten Anfragen.")
    anfrage = await session.get(Unterstuetzungsanfrage, anfrage_id)
    if anfrage is None or anfrage.empfaenger_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    anfrage.gesehen_am = datetime.utcnow()
    session.add(anfrage)
    await session.commit()
    return RedirectResponse(url="/", status_code=303)


@router.get("/teilnehmer", response_class=HTMLResponse)
async def meine_teilnehmer(request: Request, current_user: CurrentUser, session: SessionDep):
    """Gebündelte Übersicht "Meine Teilnehmer:innen" für psychosoziale
    Mitarbeiter:innen - bisher stand dafür nur eine knappe Namensliste auf
    dem Dashboard zur Verfügung, ohne Abteilung oder erkennbaren nächsten
    Schritt bei fehlender Freigabe."""
    if current_user.role != RoleEnum.psychosoziale_mitarbeit:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur psychosoziale Mitarbeiter:innen nutzen diese Ansicht.")

    zuordnung_result = await session.execute(
        select(PsmZuordnung).where(PsmZuordnung.psm_id == current_user.id)
    )
    teilnehmer_ids = [z.teilnehmer_id for z in zuordnung_result.scalars().all()]

    teilnehmer_liste: list[User] = []
    abteilung_by_id: dict[int, Abteilung] = {}
    freigegebene_ids: set[int] = set()
    if teilnehmer_ids:
        teilnehmer_result = await session.execute(
            select(User).where(User.id.in_(teilnehmer_ids)).order_by(User.name)
        )
        teilnehmer_liste = list(teilnehmer_result.scalars().all())
        abteilungs_ids = {t.abteilung_id for t in teilnehmer_liste if t.abteilung_id is not None}
        if abteilungs_ids:
            abteilung_result = await session.execute(select(Abteilung).where(Abteilung.id.in_(abteilungs_ids)))
            abteilung_by_id = {a.id: a for a in abteilung_result.scalars().all()}
        for teilnehmer_id in teilnehmer_ids:
            if await hat_wohlbefinden_freigabe(session, current_user.id, teilnehmer_id):
                freigegebene_ids.add(teilnehmer_id)

    return templates.TemplateResponse(
        request,
        "wohlbefinden/teilnehmer_liste.html",
        {
            "current_user": current_user,
            "teilnehmer_liste": teilnehmer_liste,
            "abteilung_by_id": abteilung_by_id,
            "freigegebene_ids": freigegebene_ids,
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
    energie_level: str = Form(""),
    atemuebung_name: str = Form(""),
    atemuebung_erledigt: str = Form(""),
    morgen_uebung_typ: str = Form(""),
    koerperscan_erledigt: str = Form(""),
    grounding_1: str = Form(""),
    grounding_2: str = Form(""),
    grounding_3: str = Form(""),
    grounding_4: str = Form(""),
    grounding_5: str = Form(""),
    wort_des_tages: str = Form(""),
    staerken_karte_frage: str = Form(""),
    staerken_karte_antwort: str = Form(""),
    staerken_karte_erledigt: str = Form(""),
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
    eintrag.atemuebung_name = atemuebung_name or atemuebung_des_tages(current_user.id, tag_datum)
    if energie_level:
        wert = int(energie_level)
        if not ENERGIE_LEVEL_MIN <= wert <= ENERGIE_LEVEL_MAX:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültiger Energie-Level.")
        eintrag.energie_level = wert
    if atemuebung_erledigt and eintrag.atemuebung_erledigt_am is None:
        eintrag.atemuebung_erledigt_am = datetime.utcnow()

    eintrag.morgen_uebung_typ = morgen_uebung_typ or morgenuebung_des_tages(current_user.id, tag_datum)
    if koerperscan_erledigt and eintrag.koerperscan_erledigt_am is None:
        eintrag.koerperscan_erledigt_am = datetime.utcnow()
    if any([grounding_1, grounding_2, grounding_3, grounding_4, grounding_5]) and eintrag.grounding_erledigt_am is None:
        eintrag.grounding_erledigt_am = datetime.utcnow()
    if wort_des_tages:
        eintrag.wort_des_tages = wort_des_tages
    eintrag.staerken_karte_frage = staerken_karte_frage or staerken_karte_des_tages(current_user.id, tag_datum)
    if staerken_karte_antwort:
        eintrag.staerken_karte_antwort = staerken_karte_antwort
    if staerken_karte_erledigt and eintrag.staerken_karte_erledigt_am is None:
        eintrag.staerken_karte_erledigt_am = datetime.utcnow()

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
    zeichnung_daten: str = Form(""),
    zeichnung_entfernen: str = Form(""),
    check_pause_gemacht: str = Form(""),
    check_jemandem_geholfen: str = Form(""),
    check_kleines_erfolgserlebnis: str = Form(""),
    abend_uebung_typ: str = Form(""),
    mandala_erledigt: str = Form(""),
    ruhe_ort_sehen: str = Form(""),
    ruhe_ort_hoeren: str = Form(""),
    ruhe_ort_spueren: str = Form(""),
    gedanke_belastend: str = Form(""),
    gedanke_ausgewogen: str = Form(""),
    sorgen_los_erledigt: str = Form(""),
    dankbarkeitsfoto: UploadFile | None = File(None),
    dankbarkeitsfoto_entfernen: str = Form(""),
    mini_ziel_text: str = Form(""),
    mini_ziel_geschafft: str = Form(""),
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
    eintrag.check_pause_gemacht = bool(check_pause_gemacht)
    eintrag.check_jemandem_geholfen = bool(check_jemandem_geholfen)
    eintrag.check_kleines_erfolgserlebnis = bool(check_kleines_erfolgserlebnis)

    if zeichnung_entfernen and eintrag.zeichnung_pfad:
        datei_loeschen(eintrag.zeichnung_pfad)
        eintrag.zeichnung_pfad = None
    elif zeichnung_daten:
        if eintrag.zeichnung_pfad:
            datei_loeschen(eintrag.zeichnung_pfad)
        eintrag.zeichnung_pfad = await _zeichnung_speichern(current_user.id, zeichnung_daten)

    eintrag.abend_uebung_typ = abend_uebung_typ or abenduebung_des_tages(current_user.id, tag_datum)
    if mandala_erledigt and eintrag.mandala_erledigt_am is None:
        eintrag.mandala_erledigt_am = datetime.utcnow()
    if ruhe_ort_sehen:
        eintrag.ruhe_ort_sehen = ruhe_ort_sehen
    if ruhe_ort_hoeren:
        eintrag.ruhe_ort_hoeren = ruhe_ort_hoeren
    if ruhe_ort_spueren:
        eintrag.ruhe_ort_spueren = ruhe_ort_spueren
    if gedanke_belastend:
        eintrag.gedanke_belastend = gedanke_belastend
    if gedanke_ausgewogen:
        eintrag.gedanke_ausgewogen = gedanke_ausgewogen
    if sorgen_los_erledigt and eintrag.sorgen_los_erledigt_am is None:
        eintrag.sorgen_los_erledigt_am = datetime.utcnow()

    if dankbarkeitsfoto_entfernen and eintrag.dankbarkeitsfoto_pfad:
        datei_loeschen(eintrag.dankbarkeitsfoto_pfad)
        eintrag.dankbarkeitsfoto_pfad = None
    elif dankbarkeitsfoto is not None and dankbarkeitsfoto.filename:
        if eintrag.dankbarkeitsfoto_pfad:
            datei_loeschen(eintrag.dankbarkeitsfoto_pfad)
        _, speicherpfad, _ = await datei_speichern(dankbarkeitsfoto, f"tagebuch/{current_user.id}")
        eintrag.dankbarkeitsfoto_pfad = speicherpfad

    if mini_ziel_text:
        eintrag.mini_ziel_text = mini_ziel_text
    eintrag.mini_ziel_geschafft = bool(mini_ziel_geschafft)

    eintrag.abend_ausgefuellt_am = datetime.utcnow()
    session.add(eintrag)
    await session.commit()
    return RedirectResponse(url=f"/wohlbefinden?tag={datum}", status_code=303)


@router.get("/zeichnung/{eintrag_id}")
async def zeichnung_anzeigen(eintrag_id: int, current_user: CurrentUser, session: SessionDep):
    eintrag = await session.get(TagebuchEintrag, eintrag_id)
    if eintrag is None or not eintrag.zeichnung_pfad:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, eintrag.teilnehmer_id, "Kein Zugriff auf diese Zeichnung.")

    inhalt = await datei_lesen_entschluesselt(eintrag.zeichnung_pfad)
    return Response(content=inhalt, media_type="image/png")


@router.get("/dankbarkeitsfoto/{eintrag_id}")
async def dankbarkeitsfoto_anzeigen(eintrag_id: int, current_user: CurrentUser, session: SessionDep):
    eintrag = await session.get(TagebuchEintrag, eintrag_id)
    if eintrag is None or not eintrag.dankbarkeitsfoto_pfad:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, eintrag.teilnehmer_id, "Kein Zugriff auf dieses Foto.")

    inhalt = await datei_lesen_entschluesselt(eintrag.dankbarkeitsfoto_pfad)
    endung = Path(eintrag.dankbarkeitsfoto_pfad).suffix.lower()
    media_type = "image/png" if endung == ".png" else "image/jpeg"
    return Response(content=inhalt, media_type=media_type)


@router.post("/tag/loeschen")
async def tag_loeschen(current_user: CurrentUser, session: SessionDep, datum: str = Form(...)):
    tag_datum = date.fromisoformat(datum)
    eintrag = await _hole_eintrag(session, current_user.id, tag_datum)
    if eintrag is not None:
        require_owner(current_user, eintrag.teilnehmer_id, "Kein Zugriff auf diesen Eintrag.")
        if eintrag.zeichnung_pfad:
            datei_loeschen(eintrag.zeichnung_pfad)
        if eintrag.dankbarkeitsfoto_pfad:
            datei_loeschen(eintrag.dankbarkeitsfoto_pfad)
        await session.delete(eintrag)
        await session.commit()
    return RedirectResponse(url=f"/wohlbefinden?tag={datum}", status_code=303)
