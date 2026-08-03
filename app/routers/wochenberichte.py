from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlmodel import select

from app.core.access import (
    betreute_teilnehmer_ids,
    karte_ist_sichtbar_fuer,
    require_owner,
    require_role,
    sichtbare_board_ids_fuer_teilnehmer,
)
from app.core.deps import CurrentUser, SessionDep, verify_csrf
from app.core.templating import templates
from app.core.wochenbericht_export import wochenbericht_als_docx
from app.models.kanban import Board, Karte, Spalte
from app.models.user import RoleEnum, User
from app.models.wochenbericht import WOCHENTAG_LABELS, WOCHENTAGE, Wochenbericht, WochenberichtStatus, leere_tage

WORD_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

router = APIRouter(prefix="/wochenberichte", tags=["wochenberichte"], dependencies=[Depends(verify_csrf)])


def _wochenstart(kw_jahr: int, kw_nummer: int) -> date:
    return date.fromisocalendar(kw_jahr, kw_nummer, 1)


def _tage_aus_formularfeldern(
    montag: tuple[str, str, str],
    dienstag: tuple[str, str, str],
    mittwoch: tuple[str, str, str],
    donnerstag: tuple[str, str, str],
    freitag: tuple[str, str, str],
) -> dict:
    """Baut das `Wochenbericht.tage`-JSON aus den (Beginn, Ende, Tätigkeiten)-
    Tripeln der fünf Werktage - von bericht_erstellen UND bericht_bearbeiten
    genutzt, damit diese Zuordnung nur an einer Stelle gepflegt wird."""
    tagesfelder = {
        "montag": montag,
        "dienstag": dienstag,
        "mittwoch": mittwoch,
        "donnerstag": donnerstag,
        "freitag": freitag,
    }
    tage = leere_tage()
    for tag, (start, ende, taetigkeiten) in tagesfelder.items():
        tage[tag] = {"start": start or None, "ende": ende or None, "taetigkeiten": taetigkeiten or None}
    return tage


def _tage_mit_datum(bericht: Wochenbericht) -> list[dict]:
    start = _wochenstart(bericht.kw_jahr, bericht.kw_nummer)
    ergebnis = []
    for i, tag in enumerate(WOCHENTAGE):
        eintrag = bericht.tage.get(tag, {})
        ergebnis.append(
            {
                "key": tag,
                "datum": start.fromordinal(start.toordinal() + i),
                "start": eintrag.get("start"),
                "ende": eintrag.get("ende"),
                "taetigkeiten": eintrag.get("taetigkeiten"),
            }
        )
    return ergebnis


async def _erledigte_kanban_karten_diese_woche(session: SessionDep, current_user: CurrentUser) -> dict[str, list[str]]:
    """Titel der Kanban-Karten, die in der laufenden Kalenderwoche
    abgeschlossen wurden, je Wochentag - als unverbindliche Vorschläge im
    "Neuer Wochenbericht"-Formular (siehe teilnehmer_uebersicht.html), damit
    nicht dieselbe Information doppelt eingetippt werden muss."""
    je_tag: dict[str, list[str]] = {tag: [] for tag in WOCHENTAGE}
    board_ids = await sichtbare_board_ids_fuer_teilnehmer(session, current_user.id)
    if not board_ids:
        return je_tag

    heute = date.today()
    wochenstart = heute - timedelta(days=heute.weekday())
    wochenende = wochenstart + timedelta(days=4)

    result = await session.execute(
        select(Karte, Board)
        .join(Spalte, Spalte.id == Karte.spalte_id)
        .join(Board, Board.id == Spalte.board_id)
        .where(Spalte.board_id.in_(board_ids), Karte.abgeschlossen_am.is_not(None))
    )
    for karte, board in result.all():
        if not karte_ist_sichtbar_fuer(current_user, board, karte):
            continue
        abgeschlossen_datum = karte.abgeschlossen_am.date()
        if not (wochenstart <= abgeschlossen_datum <= wochenende):
            continue
        je_tag[WOCHENTAGE[abgeschlossen_datum.weekday()]].append(karte.titel)
    return je_tag


@router.get("", response_class=HTMLResponse)
async def uebersicht(request: Request, current_user: CurrentUser, session: SessionDep):
    if current_user.role == RoleEnum.teilnehmer:
        result = await session.execute(
            select(Wochenbericht)
            .where(Wochenbericht.teilnehmer_id == current_user.id)
            .order_by(Wochenbericht.kw_jahr.desc(), Wochenbericht.kw_nummer.desc())
        )
        berichte = list(result.scalars().all())
        berichte_anzeige = [{"bericht": b, "tage": _tage_mit_datum(b)} for b in berichte]
        heute = date.today()
        aktuelle_kw = f"{heute.isocalendar().year}-W{heute.isocalendar().week:02d}"
        kanban_vorschlaege = await _erledigte_kanban_karten_diese_woche(session, current_user)
        return templates.TemplateResponse(
            request,
            "wochenberichte/teilnehmer_uebersicht.html",
            {
                "current_user": current_user,
                "berichte_anzeige": berichte_anzeige,
                "wochentage": WOCHENTAGE,
                "tag_labels": WOCHENTAG_LABELS,
                "aktuelle_kw": aktuelle_kw,
                "kanban_vorschlaege": kanban_vorschlaege,
            },
        )

    if current_user.role == RoleEnum.berufstrainer:
        teilnehmer_ids = await betreute_teilnehmer_ids(session, current_user.id)
        berichte_anzeige = []
        teilnehmer_by_id: dict[int, User] = {}
        if teilnehmer_ids:
            result = await session.execute(
                select(Wochenbericht)
                .where(
                    Wochenbericht.teilnehmer_id.in_(teilnehmer_ids),
                    Wochenbericht.status == WochenberichtStatus.abgegeben,
                )
                .order_by(Wochenbericht.kw_jahr.desc(), Wochenbericht.kw_nummer.desc())
            )
            berichte = list(result.scalars().all())
            berichte_anzeige = [{"bericht": b, "tage": _tage_mit_datum(b)} for b in berichte]
            teilnehmer_result = await session.execute(select(User).where(User.id.in_(teilnehmer_ids)))
            teilnehmer_by_id = {t.id: t for t in teilnehmer_result.scalars().all()}
        return templates.TemplateResponse(
            request,
            "wochenberichte/trainer_uebersicht.html",
            {"current_user": current_user, "berichte_anzeige": berichte_anzeige, "teilnehmer_by_id": teilnehmer_by_id},
        )

    return templates.TemplateResponse(
        request, "wochenberichte/kein_zugriff.html", {"current_user": current_user}, status_code=403
    )


@router.post("")
async def bericht_erstellen(
    current_user: CurrentUser,
    session: SessionDep,
    woche: str = Form(...),
    besonderheiten: str = Form(""),
    start_montag: str = Form(""),
    ende_montag: str = Form(""),
    taetigkeiten_montag: str = Form(""),
    start_dienstag: str = Form(""),
    ende_dienstag: str = Form(""),
    taetigkeiten_dienstag: str = Form(""),
    start_mittwoch: str = Form(""),
    ende_mittwoch: str = Form(""),
    taetigkeiten_mittwoch: str = Form(""),
    start_donnerstag: str = Form(""),
    ende_donnerstag: str = Form(""),
    taetigkeiten_donnerstag: str = Form(""),
    start_freitag: str = Form(""),
    ende_freitag: str = Form(""),
    taetigkeiten_freitag: str = Form(""),
):
    require_role(current_user, RoleEnum.teilnehmer, "Nur Teilnehmer:innen schreiben Wochenberichte.")

    try:
        jahr_str, kw_str = woche.split("-W")
        kw_jahr, kw_nummer = int(jahr_str), int(kw_str)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Kalenderwoche.") from exc
    if not 1 <= kw_nummer <= 53:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kalenderwoche muss zwischen 1 und 53 liegen.")

    tage = _tage_aus_formularfeldern(
        (start_montag, ende_montag, taetigkeiten_montag),
        (start_dienstag, ende_dienstag, taetigkeiten_dienstag),
        (start_mittwoch, ende_mittwoch, taetigkeiten_mittwoch),
        (start_donnerstag, ende_donnerstag, taetigkeiten_donnerstag),
        (start_freitag, ende_freitag, taetigkeiten_freitag),
    )

    session.add(
        Wochenbericht(
            teilnehmer_id=current_user.id,
            kw_jahr=kw_jahr,
            kw_nummer=kw_nummer,
            tage=tage,
            besonderheiten=besonderheiten or None,
        )
    )
    await session.commit()
    return RedirectResponse(url="/wochenberichte", status_code=303)


@router.post("/{bericht_id}/bearbeiten")
async def bericht_bearbeiten(
    bericht_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    besonderheiten: str = Form(""),
    start_montag: str = Form(""),
    ende_montag: str = Form(""),
    taetigkeiten_montag: str = Form(""),
    start_dienstag: str = Form(""),
    ende_dienstag: str = Form(""),
    taetigkeiten_dienstag: str = Form(""),
    start_mittwoch: str = Form(""),
    ende_mittwoch: str = Form(""),
    taetigkeiten_mittwoch: str = Form(""),
    start_donnerstag: str = Form(""),
    ende_donnerstag: str = Form(""),
    taetigkeiten_donnerstag: str = Form(""),
    start_freitag: str = Form(""),
    ende_freitag: str = Form(""),
    taetigkeiten_freitag: str = Form(""),
):
    bericht = await session.get(Wochenbericht, bericht_id)
    if bericht is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, bericht.teilnehmer_id, "Kein Zugriff auf diesen Wochenbericht.")
    if bericht.status != WochenberichtStatus.entwurf:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Abgegebene Wochenberichte können nicht mehr bearbeitet werden."
        )

    tage = _tage_aus_formularfeldern(
        (start_montag, ende_montag, taetigkeiten_montag),
        (start_dienstag, ende_dienstag, taetigkeiten_dienstag),
        (start_mittwoch, ende_mittwoch, taetigkeiten_mittwoch),
        (start_donnerstag, ende_donnerstag, taetigkeiten_donnerstag),
        (start_freitag, ende_freitag, taetigkeiten_freitag),
    )

    bericht.tage = tage
    bericht.besonderheiten = besonderheiten or None
    session.add(bericht)
    await session.commit()
    return RedirectResponse(url="/wochenberichte", status_code=303)


@router.post("/{bericht_id}/abgeben")
async def bericht_abgeben(bericht_id: int, current_user: CurrentUser, session: SessionDep):
    bericht = await session.get(Wochenbericht, bericht_id)
    if bericht is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, bericht.teilnehmer_id, "Kein Zugriff auf diesen Wochenbericht.")

    bericht.status = WochenberichtStatus.abgegeben
    bericht.abgegeben_am = datetime.utcnow()
    session.add(bericht)
    await session.commit()
    return RedirectResponse(url="/wochenberichte", status_code=303)


@router.post("/{bericht_id}/loeschen")
async def bericht_loeschen(bericht_id: int, current_user: CurrentUser, session: SessionDep):
    bericht = await session.get(Wochenbericht, bericht_id)
    if bericht is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, bericht.teilnehmer_id, "Kein Zugriff auf diesen Wochenbericht.")
    if bericht.status != WochenberichtStatus.entwurf:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Abgegebene Wochenberichte können nicht gelöscht werden.")

    await session.delete(bericht)
    await session.commit()
    return RedirectResponse(url="/wochenberichte", status_code=303)


@router.get("/{bericht_id}/word")
async def bericht_word_export(bericht_id: int, current_user: CurrentUser, session: SessionDep):
    bericht = await session.get(Wochenbericht, bericht_id)
    if bericht is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    if current_user.id != bericht.teilnehmer_id:
        if current_user.role != RoleEnum.berufstrainer:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Kein Zugriff auf diesen Wochenbericht.")
        betreute_ids = await betreute_teilnehmer_ids(session, current_user.id)
        if bericht.teilnehmer_id not in betreute_ids or bericht.status != WochenberichtStatus.abgegeben:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Kein Zugriff auf diesen Wochenbericht.")

    teilnehmer = await session.get(User, bericht.teilnehmer_id)
    wochenstart = _wochenstart(bericht.kw_jahr, bericht.kw_nummer)
    dokument = wochenbericht_als_docx(bericht, teilnehmer.name, wochenstart)

    dateiname = f"Wochenbericht_KW{bericht.kw_nummer:02d}-{bericht.kw_jahr}_{teilnehmer.name.replace(' ', '_')}.docx"
    return Response(
        content=dokument,
        media_type=WORD_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )
