"""Zentrale Autorisierungs-Schicht.

Alle Router prüfen Zugriff ausschließlich über diese Funktionen - keine
verstreute if-Rolle-Logik in einzelnen Endpoints (siehe CLAUDE.md,
Abschnitt "Datenbank" / "Sicherheit").
"""

from datetime import date

from fastapi import HTTPException, status
from sqlmodel import or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.bewerbung import Bewerbung, BewerbungsFreigabe, BewerbungsFreigabeUmfang
from app.models.kanban import Board, BoardFreigabe, BoardTyp, Karte, KartenSichtbarkeit
from app.models.organisation import (
    BerufstrainerZuordnung,
    HandlungsfeldLeitung,
    HandlungsfeldMitglied,
    Teilnehmergruppe,
    TeilnehmergruppeMitglied,
)
from app.models.user import RoleEnum, User
from app.models.wohlbefinden import WohlbefindenFreigabe


async def ist_leiter_von_handlungsfeld(session: AsyncSession, berufstrainer_id: int, handlungsfeld_id: int) -> bool:
    result = await session.execute(
        select(HandlungsfeldLeitung).where(
            HandlungsfeldLeitung.berufstrainer_id == berufstrainer_id,
            HandlungsfeldLeitung.handlungsfeld_id == handlungsfeld_id,
        )
    )
    return result.first() is not None


async def geleitete_handlungsfeld_ids(session: AsyncSession, berufstrainer_id: int) -> list[int]:
    result = await session.execute(
        select(HandlungsfeldLeitung.handlungsfeld_id).where(
            HandlungsfeldLeitung.berufstrainer_id == berufstrainer_id
        )
    )
    return list(result.scalars().all())


async def betreute_teilnehmer_ids(session: AsyncSession, berufstrainer_id: int) -> list[int]:
    """Teilnehmer:innen, die einer Gruppe eines von diesem Trainer geleiteten
    Handlungsfelds angehören - z.B. relevant für die Sichtbarkeit
    abgegebener Wochenberichte (siehe app/routers/wochenberichte.py).

    Bewusst über die bestehende Handlungsfeld-/Gruppenstruktur abgeleitet,
    statt eine weitere separate Zuordnungstabelle einzuführen.
    """
    handlungsfeld_ids = await geleitete_handlungsfeld_ids(session, berufstrainer_id)
    if not handlungsfeld_ids:
        return []
    result = await session.execute(
        select(TeilnehmergruppeMitglied.teilnehmer_id)
        .join(Teilnehmergruppe, Teilnehmergruppe.id == TeilnehmergruppeMitglied.gruppe_id)
        .where(Teilnehmergruppe.handlungsfeld_id.in_(handlungsfeld_ids))
        .distinct()
    )
    return list(result.scalars().all())


async def teilnehmer_hat_boardzugriff(session: AsyncSession, teilnehmer_id: int, board_id: int) -> bool:
    result = await session.execute(
        select(BoardFreigabe)
        .join(
            TeilnehmergruppeMitglied,
            TeilnehmergruppeMitglied.gruppe_id == BoardFreigabe.gruppe_id,
        )
        .where(
            BoardFreigabe.board_id == board_id,
            TeilnehmergruppeMitglied.teilnehmer_id == teilnehmer_id,
        )
    )
    return result.first() is not None


async def ist_mitglied_von_handlungsfeld(session: AsyncSession, teilnehmer_id: int, handlungsfeld_id: int) -> bool:
    result = await session.execute(
        select(HandlungsfeldMitglied).where(
            HandlungsfeldMitglied.teilnehmer_id == teilnehmer_id,
            HandlungsfeldMitglied.handlungsfeld_id == handlungsfeld_id,
        )
    )
    return result.first() is not None


async def handlungsfeld_ids_von_teilnehmer(session: AsyncSession, teilnehmer_id: int) -> list[int]:
    result = await session.execute(
        select(HandlungsfeldMitglied.handlungsfeld_id).where(HandlungsfeldMitglied.teilnehmer_id == teilnehmer_id)
    )
    return list(result.scalars().all())


async def ist_zustaendiger_trainer(session: AsyncSession, trainer_id: int, teilnehmer_id: int) -> bool:
    """True, wenn der Trainer eines der Handlungsfelder der/des Teilnehmer:in
    leitet ODER eine explizite BerufstrainerZuordnung besteht.

    Grundlage dafür, dass ein Trainer persönliche Kanban-Items (Personen-
    Board, siehe Board.typ == person) für diese:n Teilnehmer:in anlegen und
    einsehen darf.
    """
    handlungsfeld_ids = await handlungsfeld_ids_von_teilnehmer(session, teilnehmer_id)
    if handlungsfeld_ids:
        result = await session.execute(
            select(HandlungsfeldLeitung).where(
                HandlungsfeldLeitung.berufstrainer_id == trainer_id,
                HandlungsfeldLeitung.handlungsfeld_id.in_(handlungsfeld_ids),
            )
        )
        if result.first() is not None:
            return True

    result = await session.execute(
        select(BerufstrainerZuordnung).where(
            BerufstrainerZuordnung.berufstrainer_id == trainer_id,
            BerufstrainerZuordnung.teilnehmer_id == teilnehmer_id,
        )
    )
    return result.first() is not None


async def boardmitglieder_ids(session: AsyncSession, board: Board) -> list[int]:
    """Teilnehmer:innen, denen auf diesem Board Karten zugewiesen werden
    dürfen (IDOR-Schutz für Zuweisungen). Team-Board: Mitglieder der
    freigegebenen Teilnehmergruppen. Personen-Board: nur die/der Owner.
    """
    if board.typ == BoardTyp.person:
        return [board.person_teilnehmer_id] if board.person_teilnehmer_id is not None else []

    result = await session.execute(
        select(TeilnehmergruppeMitglied.teilnehmer_id)
        .join(BoardFreigabe, BoardFreigabe.gruppe_id == TeilnehmergruppeMitglied.gruppe_id)
        .where(BoardFreigabe.board_id == board.id)
        .distinct()
    )
    return list(result.scalars().all())


def sichtbare_karten_filter(current_user: User, board: Board, karten: list[Karte]) -> list[Karte]:
    """Filtert Karten eines Personen-Boards nach Sichtbarkeit.

    Team-Boards: alle Karten sichtbar (unverändert). Personen-Boards: die/der
    Owner sieht alles; ein zuständiger Trainer sieht nur Karten mit
    sichtbarkeit=team oder solche, die er selbst erstellt hat - private
    Karten der/des Teilnehmer:in bleiben ihr/ihm vorbehalten (Privacy by
    Default, siehe CLAUDE.md §24 "Keine Überwachung").
    """
    if board.typ != BoardTyp.person or current_user.id == board.person_teilnehmer_id:
        return karten
    return [k for k in karten if k.sichtbarkeit == KartenSichtbarkeit.team or k.ersteller_id == current_user.id]


async def require_kanban_access(session: AsyncSession, current_user: User, board: Board) -> None:
    """Zentrale Zugriffsprüfung für Team- und Personen-Boards.

    Team-Board: nur die Leitung des zugehörigen Handlungsfelds verwaltet es;
    Teilnehmer haben nur Zugriff, wenn ihre Teilnehmergruppe freigegeben
    wurde. Personen-Board: die/der Teilnehmer:in (Owner) hat immer Zugriff,
    ein Trainer nur wenn er dafür zuständig ist (siehe
    ist_zustaendiger_trainer). Einrichtungs-Admins und psychosoziale
    Mitarbeit haben laut Berechtigungsmatrix keinen inhaltlichen
    Standardzugriff auf Kanban.
    """
    if board.typ == BoardTyp.person:
        if current_user.role == RoleEnum.teilnehmer and current_user.id == board.person_teilnehmer_id:
            return
        if current_user.role == RoleEnum.berufstrainer and await ist_zustaendiger_trainer(
            session, current_user.id, board.person_teilnehmer_id
        ):
            return
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Kein Zugriff auf dieses Board.")

    if current_user.role == RoleEnum.berufstrainer and await ist_leiter_von_handlungsfeld(
        session, current_user.id, board.handlungsfeld_id
    ):
        return
    if current_user.role == RoleEnum.teilnehmer and await teilnehmer_hat_boardzugriff(
        session, current_user.id, board.id
    ):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Kein Zugriff auf dieses Board.")


async def kann_board_verwalten(session: AsyncSession, current_user: User, board: Board) -> bool:
    """Wer die Struktur eines Boards verwalten darf (Spalten anlegen/umbenennen/
    löschen, Board löschen) - bewusst enger als require_kanban_access (reine
    Inhaltsnutzung).

    Team-Board: nur die Leitung des Handlungsfelds. Personen-Board: nur die/der
    Teilnehmer:in selbst (nicht der zuständige Trainer) - die Struktur der
    eigenen Aufgabenliste bleibt Selbstbestimmung, siehe CLAUDE.md §1
    "Selbstbestimmung vor Fürsorge".
    """
    if board.typ == BoardTyp.person:
        return current_user.id == board.person_teilnehmer_id
    return current_user.role == RoleEnum.berufstrainer and await ist_leiter_von_handlungsfeld(
        session, current_user.id, board.handlungsfeld_id
    )


async def require_board_verwaltung(session: AsyncSession, current_user: User, board: Board) -> None:
    if not await kann_board_verwalten(session, current_user, board):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur die Board-Verwaltung darf diese Aktion ausführen.")


def require_role(current_user: User, role: RoleEnum, message: str) -> None:
    if current_user.role != role:
        raise HTTPException(status.HTTP_403_FORBIDDEN, message)


async def hat_wohlbefinden_freigabe(session: AsyncSession, empfaenger_id: int, teilnehmer_id: int) -> bool:
    """Aktive (nicht widerrufene, nicht abgelaufene) Freigabe der/des
    Teilnehmer:in für diese PSM-Person - siehe
    app/models/wohlbefinden.py:WohlbefindenFreigabe. Ersetzt nicht die
    organisatorische PsmZuordnung, sondern ergänzt sie (beide nötig)."""
    heute = date.today()
    result = await session.execute(
        select(WohlbefindenFreigabe).where(
            WohlbefindenFreigabe.teilnehmer_id == teilnehmer_id,
            WohlbefindenFreigabe.empfaenger_id == empfaenger_id,
            WohlbefindenFreigabe.widerrufen_am.is_(None),
            or_(WohlbefindenFreigabe.gueltig_bis.is_(None), WohlbefindenFreigabe.gueltig_bis >= heute),
        )
    )
    return result.first() is not None


async def hat_bewerbungs_freigabe(session: AsyncSession, empfaenger_id: int, bewerbung: Bewerbung) -> bool:
    """Analog hat_wohlbefinden_freigabe, für Berufstrainer/Bewerbungen -
    ergänzt die organisatorische BerufstrainerZuordnung."""
    heute = date.today()
    result = await session.execute(
        select(BewerbungsFreigabe).where(
            BewerbungsFreigabe.teilnehmer_id == bewerbung.teilnehmer_id,
            BewerbungsFreigabe.empfaenger_id == empfaenger_id,
            BewerbungsFreigabe.widerrufen_am.is_(None),
            or_(BewerbungsFreigabe.gueltig_bis.is_(None), BewerbungsFreigabe.gueltig_bis >= heute),
            or_(
                BewerbungsFreigabe.umfang == BewerbungsFreigabeUmfang.alle,
                BewerbungsFreigabe.bewerbung_id == bewerbung.id,
            ),
        )
    )
    return result.first() is not None


def require_owner(current_user: User, resource_owner_id: int, message: str) -> None:
    """Für Wohlbefinden/Bewerbungen: in diesem Prototyp NUR der Owner.

    Das Freigabe-System (Phase 2) ist noch nicht implementiert - bis dahin
    ist "nur der Owner" die einzig korrekte Voreinstellung (Privacy by
    Default statt verfrühtem Betreuerzugriff ohne Consent-Mechanismus).
    """
    if current_user.id != resource_owner_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, message)
