"""Zentrale Übersicht für Teilnehmer:innen: alle eigenen aktiven Freigaben
(Wohlbefinden + Bewerbungen) an einem Ort mit Sofort-Widerruf, plus die
eigene Audit-Log-Ansicht ("Wer hat wann auf meine Daten zugegriffen",
siehe DATENSCHUTZ_UND_BERECHTIGUNGEN.md §2.4).

Widerruf selbst passiert weiterhin über die domänenspezifischen Endpoints
in app/routers/wohlbefinden.py bzw. app/routers/bewerbungen.py - hier wird
nur gebündelt dargestellt.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select

from app.core.deletion import (
    loesche_alle_bewerbungsdaten,
    loesche_alle_wohlbefinden_daten,
    loesche_persoenliches_kanban_board,
)
from app.core.deps import CurrentUser, SessionDep, verify_csrf
from app.core.templating import templates
from app.models.audit import AuditLogEintrag
from app.models.bewerbung import Bewerbung, BewerbungsFreigabe
from app.models.kanban import Board, BoardFreigabe
from app.models.organisation import HandlungsfeldMitglied, Teilnehmergruppe, TeilnehmergruppeMitglied
from app.models.user import RoleEnum, User
from app.models.wohlbefinden import WohlbefindenFreigabe

router = APIRouter(prefix="/freigaben", tags=["freigaben"], dependencies=[Depends(verify_csrf)])

BESTAETIGUNGSWORT = "LÖSCHEN"


@router.get("", response_class=HTMLResponse)
async def meine_freigaben(request: Request, current_user: CurrentUser, session: SessionDep):
    if current_user.role != RoleEnum.teilnehmer:
        return templates.TemplateResponse(
            request,
            "freigaben/kein_zugriff.html",
            {"current_user": current_user},
            status_code=403,
        )

    wohlbefinden_result = await session.execute(
        select(WohlbefindenFreigabe)
        .where(WohlbefindenFreigabe.teilnehmer_id == current_user.id, WohlbefindenFreigabe.widerrufen_am.is_(None))
        .order_by(WohlbefindenFreigabe.erstellt_am.desc())
    )
    wohlbefinden_freigaben = list(wohlbefinden_result.scalars().all())

    bewerbungs_result = await session.execute(
        select(BewerbungsFreigabe)
        .where(BewerbungsFreigabe.teilnehmer_id == current_user.id, BewerbungsFreigabe.widerrufen_am.is_(None))
        .order_by(BewerbungsFreigabe.erstellt_am.desc())
    )
    bewerbungs_freigaben = list(bewerbungs_result.scalars().all())

    empfaenger_ids = {f.empfaenger_id for f in wohlbefinden_freigaben} | {
        f.empfaenger_id for f in bewerbungs_freigaben
    }
    empfaenger_by_id: dict[int, User] = {}
    if empfaenger_ids:
        empfaenger_result = await session.execute(select(User).where(User.id.in_(empfaenger_ids)))
        empfaenger_by_id = {u.id: u for u in empfaenger_result.scalars().all()}

    bewerbung_ids = {f.bewerbung_id for f in bewerbungs_freigaben if f.bewerbung_id is not None}
    bewerbung_by_id: dict[int, Bewerbung] = {}
    if bewerbung_ids:
        bewerbung_result = await session.execute(select(Bewerbung).where(Bewerbung.id.in_(bewerbung_ids)))
        bewerbung_by_id = {b.id: b for b in bewerbung_result.scalars().all()}

    board_freigaben: list[dict] = []

    gruppe_freigaben_result = await session.execute(
        select(Board.titel, Teilnehmergruppe.name)
        .select_from(BoardFreigabe)
        .join(Board, Board.id == BoardFreigabe.board_id)
        .join(Teilnehmergruppe, Teilnehmergruppe.id == BoardFreigabe.gruppe_id)
        .join(TeilnehmergruppeMitglied, TeilnehmergruppeMitglied.gruppe_id == BoardFreigabe.gruppe_id)
        .where(TeilnehmergruppeMitglied.teilnehmer_id == current_user.id)
        .distinct()
    )
    board_freigaben += [
        {"board_titel": t, "art": f"Arbeitsgruppe: {g}"} for t, g in gruppe_freigaben_result.all()
    ]

    handlungsfeld_freigaben_result = await session.execute(
        select(Board.titel)
        .select_from(BoardFreigabe)
        .join(Board, Board.id == BoardFreigabe.board_id)
        .join(HandlungsfeldMitglied, HandlungsfeldMitglied.handlungsfeld_id == BoardFreigabe.handlungsfeld_id)
        .where(HandlungsfeldMitglied.teilnehmer_id == current_user.id)
        .distinct()
    )
    board_freigaben += [
        {"board_titel": titel, "art": "Ganzes Handlungsfeld"} for (titel,) in handlungsfeld_freigaben_result.all()
    ]

    direkte_freigaben_result = await session.execute(
        select(Board.titel)
        .select_from(BoardFreigabe)
        .join(Board, Board.id == BoardFreigabe.board_id)
        .where(BoardFreigabe.teilnehmer_id == current_user.id)
    )
    board_freigaben += [{"board_titel": titel, "art": "Persönlich an dich"} for (titel,) in direkte_freigaben_result.all()]

    board_freigaben.sort(key=lambda f: f["board_titel"])

    audit_result = await session.execute(
        select(AuditLogEintrag)
        .where(AuditLogEintrag.ziel_teilnehmer_id == current_user.id)
        .order_by(AuditLogEintrag.zeitpunkt.desc())
        .limit(100)
    )
    audit_eintraege = list(audit_result.scalars().all())
    akteur_ids = {e.akteur_id for e in audit_eintraege}
    akteur_by_id: dict[int, User] = {}
    if akteur_ids:
        akteur_result = await session.execute(select(User).where(User.id.in_(akteur_ids)))
        akteur_by_id = {u.id: u for u in akteur_result.scalars().all()}

    return templates.TemplateResponse(
        request,
        "freigaben/meine_freigaben.html",
        {
            "current_user": current_user,
            "wohlbefinden_freigaben": wohlbefinden_freigaben,
            "bewerbungs_freigaben": bewerbungs_freigaben,
            "board_freigaben": board_freigaben,
            "empfaenger_by_id": empfaenger_by_id,
            "bewerbung_by_id": bewerbung_by_id,
            "audit_eintraege": audit_eintraege,
            "akteur_by_id": akteur_by_id,
        },
    )


def _pruefe_bestaetigung(bestaetigung: str) -> None:
    if bestaetigung.strip().upper() != BESTAETIGUNGSWORT:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Bitte zur Bestätigung genau '{BESTAETIGUNGSWORT}' eingeben."
        )


@router.post("/konto/wohlbefinden-loeschen")
async def wohlbefinden_konto_loeschen(current_user: CurrentUser, session: SessionDep, bestaetigung: str = Form(...)):
    """Löscht alle eigenen Wohlbefinden-Daten unwiderruflich (Hard-Delete).
    Der Zugang (Login) bleibt bestehen - siehe app/core/deletion.py."""
    if current_user.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    _pruefe_bestaetigung(bestaetigung)

    await loesche_alle_wohlbefinden_daten(session, current_user.id)
    return RedirectResponse(url="/freigaben", status_code=303)


@router.post("/konto/bewerbungen-loeschen")
async def bewerbungen_konto_loeschen(current_user: CurrentUser, session: SessionDep, bestaetigung: str = Form(...)):
    """Löscht alle eigenen Bewerbungsdaten inkl. Dateien unwiderruflich
    (Hard-Delete). Der Zugang (Login) bleibt bestehen - siehe
    app/core/deletion.py."""
    if current_user.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    _pruefe_bestaetigung(bestaetigung)

    await loesche_alle_bewerbungsdaten(session, current_user.id)
    return RedirectResponse(url="/freigaben", status_code=303)


@router.post("/konto/kanban-loeschen")
async def kanban_konto_loeschen(current_user: CurrentUser, session: SessionDep, bestaetigung: str = Form(...)):
    """Löscht die persönliche Kanban-Aufgabenliste unwiderruflich (Hard-
    Delete). Geteilte Team-Boards und der Zugang (Login) bleiben bestehen -
    siehe app/core/deletion.py."""
    if current_user.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    _pruefe_bestaetigung(bestaetigung)

    await loesche_persoenliches_kanban_board(session, current_user.id)
    return RedirectResponse(url="/freigaben", status_code=303)
