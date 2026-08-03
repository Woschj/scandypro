"""Modulübergreifende "Was steht an"-Übersicht für das Dashboard (siehe
app/main.py:dashboard, app/templates/dashboard.html) - bündelt fällige/
überfällige Kanban-Karten über alle für die Person sichtbaren Boards hinweg,
statt dass Fälligkeiten nur einzeln auf der jeweiligen Karte sichtbar sind.

Bewusst kein rotes Warnsymbol bei Überfälligkeit (siehe CLAUDE.md §24) - nur
ein neutrales Kennzeichen, das das Template selbst sanft formatiert."""

from datetime import date, timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import (
    geleitete_team_board_ids,
    karte_ist_sichtbar_fuer,
    sichtbare_board_ids_fuer_teilnehmer,
)
from app.models.bewerbung import Bewerbung
from app.models.kanban import Board, Karte, Spalte
from app.models.user import RoleEnum, User

TAGE_VORAUS = 7
MAX_EINTRAEGE = 5


async def _faellige_kanban_karten(session: AsyncSession, current_user: User, grenze: date) -> list[dict]:
    if current_user.role == RoleEnum.teilnehmer:
        board_ids = await sichtbare_board_ids_fuer_teilnehmer(session, current_user.id)
    elif current_user.role == RoleEnum.berufstrainer:
        board_ids = await geleitete_team_board_ids(session, current_user.id)
    else:
        return []
    if not board_ids:
        return []

    result = await session.execute(
        select(Karte, Board)
        .join(Spalte, Spalte.id == Karte.spalte_id)
        .join(Board, Board.id == Spalte.board_id)
        .where(
            Spalte.board_id.in_(board_ids),
            Spalte.ist_system_erledigt == False,  # noqa: E712 - SQLAlchemy-Ausdruck, kein Python-Vergleich
            Karte.faelligkeit.is_not(None),
            Karte.faelligkeit <= grenze,
        )
    )

    eintraege = []
    for karte, board in result.all():
        if not karte_ist_sichtbar_fuer(current_user, board, karte):
            continue
        eintraege.append(
            {
                "titel": karte.titel,
                "datum": karte.faelligkeit,
                "link": f"/kanban/boards/{board.id}",
                "kontext": board.titel,
            }
        )
    return eintraege


async def _anstehende_bewerbungstermine(session: AsyncSession, current_user: User, grenze: date) -> list[dict]:
    if current_user.role != RoleEnum.teilnehmer:
        return []
    result = await session.execute(
        select(Bewerbung).where(
            Bewerbung.teilnehmer_id == current_user.id,
            Bewerbung.naechster_termin.is_not(None),
            Bewerbung.naechster_termin <= grenze,
        )
    )
    return [
        {
            "titel": f"Termin: {b.firma}",
            "datum": b.naechster_termin,
            "link": "/bewerbungen",
            "kontext": f"{b.naechster_termin_uhrzeit} Uhr" if b.naechster_termin_uhrzeit else "Bewerbung",
        }
        for b in result.scalars().all()
    ]


async def faellige_karten(session: AsyncSession, current_user: User) -> list[dict]:
    heute = date.today()
    grenze = heute + timedelta(days=TAGE_VORAUS)

    eintraege = await _faellige_kanban_karten(session, current_user, grenze)
    eintraege += await _anstehende_bewerbungstermine(session, current_user, grenze)
    for eintrag in eintraege:
        eintrag["ueberfaellig"] = eintrag["datum"] < heute
    eintraege.sort(key=lambda e: e["datum"])
    return eintraege[:MAX_EINTRAEGE]
