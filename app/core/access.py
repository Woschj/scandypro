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
from app.models.wohlbefinden import WohlbefindenFreigabe, WohlbefindenFreigabeUmfang


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
    """Zugriff über eine von drei Freigabe-Arten (siehe app/models/kanban.py:
    BoardFreigabe): eigene Arbeitsgruppe, ganzes Handlungsfeld (direkte
    Mitgliedschaft, siehe HandlungsfeldMitglied) oder individuelle
    Freigabe an genau diese Person."""
    direkt_result = await session.execute(
        select(BoardFreigabe).where(
            BoardFreigabe.board_id == board_id, BoardFreigabe.teilnehmer_id == teilnehmer_id
        )
    )
    if direkt_result.first() is not None:
        return True

    gruppe_result = await session.execute(
        select(BoardFreigabe)
        .join(TeilnehmergruppeMitglied, TeilnehmergruppeMitglied.gruppe_id == BoardFreigabe.gruppe_id)
        .where(BoardFreigabe.board_id == board_id, TeilnehmergruppeMitglied.teilnehmer_id == teilnehmer_id)
    )
    if gruppe_result.first() is not None:
        return True

    handlungsfeld_result = await session.execute(
        select(BoardFreigabe)
        .join(HandlungsfeldMitglied, HandlungsfeldMitglied.handlungsfeld_id == BoardFreigabe.handlungsfeld_id)
        .where(BoardFreigabe.board_id == board_id, HandlungsfeldMitglied.teilnehmer_id == teilnehmer_id)
    )
    return handlungsfeld_result.first() is not None


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
    dürfen (IDOR-Schutz für Zuweisungen). Team-Board: Mitglieder aller drei
    Freigabe-Arten (Arbeitsgruppe, Handlungsfeld, individuell - siehe
    app/models/kanban.py:BoardFreigabe). Personen-Board: nur die/der Owner.
    """
    if board.typ == BoardTyp.person:
        return [board.person_teilnehmer_id] if board.person_teilnehmer_id is not None else []

    ids: set[int] = set()

    gruppe_result = await session.execute(
        select(TeilnehmergruppeMitglied.teilnehmer_id)
        .join(BoardFreigabe, BoardFreigabe.gruppe_id == TeilnehmergruppeMitglied.gruppe_id)
        .where(BoardFreigabe.board_id == board.id)
        .distinct()
    )
    ids.update(gruppe_result.scalars().all())

    handlungsfeld_result = await session.execute(
        select(HandlungsfeldMitglied.teilnehmer_id)
        .join(BoardFreigabe, BoardFreigabe.handlungsfeld_id == HandlungsfeldMitglied.handlungsfeld_id)
        .where(BoardFreigabe.board_id == board.id)
        .distinct()
    )
    ids.update(handlungsfeld_result.scalars().all())

    direkt_result = await session.execute(
        select(BoardFreigabe.teilnehmer_id).where(
            BoardFreigabe.board_id == board.id, BoardFreigabe.teilnehmer_id.is_not(None)
        )
    )
    ids.update(direkt_result.scalars().all())

    return list(ids)


def karte_ist_sichtbar_fuer(current_user: User, board: Board, karte: Karte) -> bool:
    if board.typ != BoardTyp.person or current_user.id == board.person_teilnehmer_id:
        return True
    return karte.sichtbarkeit == KartenSichtbarkeit.team or karte.ersteller_id == current_user.id


def sichtbare_karten_filter(current_user: User, board: Board, karten: list[Karte]) -> list[Karte]:
    """Filtert Karten eines Personen-Boards nach Sichtbarkeit.

    Team-Boards: alle Karten sichtbar (unverändert). Personen-Boards: die/der
    Owner sieht alles; ein zuständiger Trainer sieht nur Karten mit
    sichtbarkeit=team oder solche, die er selbst erstellt hat - private
    Karten der/des Teilnehmer:in bleiben ihr/ihm vorbehalten (Privacy by
    Default, siehe CLAUDE.md §24 "Keine Überwachung").
    """
    return [k for k in karten if karte_ist_sichtbar_fuer(current_user, board, k)]


def require_karte_sichtbar(current_user: User, board: Board, karte: Karte) -> None:
    """Wirft 403, wenn diese Karte für current_user laut
    sichtbare_karten_filter nicht sichtbar wäre (private Karte eines
    Personen-Boards). Muss zusätzlich zu require_kanban_access in jedem
    mutierenden Karten-/Unteraufgaben-Endpunkt aufgerufen werden, da die
    reine Boardzugriffsprüfung private Karten nicht ausschließt - sonst kann
    ein zuständiger Trainer über die (erratbare) karte_id private Karten
    lesen/ändern, obwohl das Modell das ausschließt (siehe app/models/
    kanban.py:Karte)."""
    if not karte_ist_sichtbar_fuer(current_user, board, karte):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Diese Karte ist privat und nicht für dich sichtbar.")


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


async def sichtbare_wohlbefinden_tage(
    session: AsyncSession, empfaenger_id: int, teilnehmer_id: int
) -> set[int] | None:
    """Welche TagebuchEintrag-IDs diese PSM-Person aktuell sehen darf.

    `None` bedeutet uneingeschränkten Zugriff (mindestens eine aktive
    Freigabe mit umfang=alle/zeitraum liegt vor); eine (ggf. leere) Menge
    bedeutet: nur einzeln freigegebene Tage (umfang=einzeln), begrenzt auf
    genau die darin enthaltenen IDs. So kann eine/ein Teilnehmer:in gezielt
    nur bestimmte Tage teilen, statt zwingend das ganze Tagebuch (siehe
    app/routers/wohlbefinden.py:tag_freigeben)."""
    heute = date.today()
    result = await session.execute(
        select(WohlbefindenFreigabe).where(
            WohlbefindenFreigabe.teilnehmer_id == teilnehmer_id,
            WohlbefindenFreigabe.empfaenger_id == empfaenger_id,
            WohlbefindenFreigabe.widerrufen_am.is_(None),
            or_(WohlbefindenFreigabe.gueltig_bis.is_(None), WohlbefindenFreigabe.gueltig_bis >= heute),
        )
    )
    freigaben = list(result.scalars().all())
    if any(f.umfang != WohlbefindenFreigabeUmfang.einzeln for f in freigaben):
        return None
    return {f.tagebuch_eintrag_id for f in freigaben if f.tagebuch_eintrag_id is not None}


async def hat_wohlbefinden_freigabe(session: AsyncSession, empfaenger_id: int, teilnehmer_id: int) -> bool:
    """Ob diese PSM-Person überhaupt irgendetwas sehen darf (mindestens ein
    Tag oder uneingeschränkt) - für die grobe Zugriffsprüfung/Anzeige, siehe
    sichtbare_wohlbefinden_tage() für die genaue Einschränkung."""
    sichtbare_ids = await sichtbare_wohlbefinden_tage(session, empfaenger_id, teilnehmer_id)
    return sichtbare_ids is None or len(sichtbare_ids) > 0


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


async def sichtbare_board_ids_fuer_teilnehmer(session: AsyncSession, teilnehmer_id: int) -> list[int]:
    """Alle Board-IDs, auf die eine/ein Teilnehmer:in Zugriff hat: das eigene
    Personen-Board (falls vorhanden) plus alle Team-Boards, die über eine
    der drei Freigabe-Arten (Arbeitsgruppe, Handlungsfeld, individuell -
    siehe app/models/kanban.py:BoardFreigabe) für sie freigegeben sind.
    Grundlage für modulübergreifende Übersichten wie die Dashboard-
    Fälligkeiten-Kachel (siehe app/core/faellige_karten.py)."""
    board_ids: set[int] = set()
    eigenes_board_result = await session.execute(
        select(Board.id).where(Board.typ == BoardTyp.person, Board.person_teilnehmer_id == teilnehmer_id)
    )
    eigenes_board_id = eigenes_board_result.scalars().first()
    if eigenes_board_id is not None:
        board_ids.add(eigenes_board_id)

    gruppe_result = await session.execute(
        select(BoardFreigabe.board_id)
        .join(TeilnehmergruppeMitglied, TeilnehmergruppeMitglied.gruppe_id == BoardFreigabe.gruppe_id)
        .where(TeilnehmergruppeMitglied.teilnehmer_id == teilnehmer_id)
        .distinct()
    )
    board_ids.update(gruppe_result.scalars().all())

    handlungsfeld_result = await session.execute(
        select(BoardFreigabe.board_id)
        .join(HandlungsfeldMitglied, HandlungsfeldMitglied.handlungsfeld_id == BoardFreigabe.handlungsfeld_id)
        .where(HandlungsfeldMitglied.teilnehmer_id == teilnehmer_id)
        .distinct()
    )
    board_ids.update(handlungsfeld_result.scalars().all())

    direkt_result = await session.execute(
        select(BoardFreigabe.board_id).where(BoardFreigabe.teilnehmer_id == teilnehmer_id)
    )
    board_ids.update(direkt_result.scalars().all())

    return list(board_ids)


async def geleitete_team_board_ids(session: AsyncSession, berufstrainer_id: int) -> list[int]:
    """Alle Team-Board-IDs, die ein Berufstrainer über seine Handlungsfeld-
    Leitung verwaltet (siehe geleitete_handlungsfeld_ids)."""
    handlungsfeld_ids = await geleitete_handlungsfeld_ids(session, berufstrainer_id)
    if not handlungsfeld_ids:
        return []
    result = await session.execute(
        select(Board.id).where(Board.typ == BoardTyp.team, Board.handlungsfeld_id.in_(handlungsfeld_ids))
    )
    return list(result.scalars().all())


def require_owner(current_user: User, resource_owner_id: int, message: str) -> None:
    """Für Wohlbefinden/Bewerbungen: in diesem Prototyp NUR der Owner.

    Das Freigabe-System (Phase 2) ist noch nicht implementiert - bis dahin
    ist "nur der Owner" die einzig korrekte Voreinstellung (Privacy by
    Default statt verfrühtem Betreuerzugriff ohne Consent-Mechanismus).
    """
    if current_user.id != resource_owner_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, message)
