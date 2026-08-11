"""Kaskadierende Hard-Delete-Routinen für Wohlbefinden-, Bewerbungs- und
persönliche Kanban-Daten (siehe CLAUDE.md §10,
DATENSCHUTZ_UND_BERECHTIGUNGEN.md §5).

Löscht das Konto (User-Zeile) selbst NICHT: Kanban-Karten auf *Team*-Boards
referenzieren `ersteller_id`/`KartenZuweisung.teilnehmer_id`/
`KartenBewegung.bewegt_von_id` ohne Kaskade-Handling (nicht nullbar, keine
ON-DELETE-Regel) - ein Hard-Delete der User-Zeile würde dort entweder gegen
die Fremdschlüssel-Constraint laufen oder für andere Teilnehmende freigegebene
Boards mitreißen. Eine vollständige Konto-Löschung inkl. Login ist bewusst
auf eine spätere Schema-Änderung (z.B. nullbare Spalten + "gelöschte:r
Nutzer:in"-Anzeige) verschoben - siehe tasks/ganzheitliche-verbesserungen/
VB-004.md. Hier werden nur die Inhaltsdaten entfernt, die ausschließlich der
löschenden Person gehören.
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.uploads import datei_loeschen
from app.models.bewerbung import Bewerbung, BewerbungsFreigabe, BewerbungsNotiz, Bewerbungsunterlage
from app.models.kanban import Board, BoardFreigabe, BoardTyp, Karte, KartenBewegung, KartenZuweisung, Spalte, Unteraufgabe
from app.models.organisation import Teilnehmergruppe, TeilnehmergruppeMitglied
from app.models.wohlbefinden import TagebuchEintrag, WohlbefindenFreigabe


async def loesche_alle_wohlbefinden_daten(session: AsyncSession, teilnehmer_id: int) -> None:
    eintraege_result = await session.execute(
        select(TagebuchEintrag).where(TagebuchEintrag.teilnehmer_id == teilnehmer_id)
    )
    for eintrag in eintraege_result.scalars().all():
        for pfad in (
            eintrag.zeichnung_pfad,
            eintrag.dankbarkeitsfoto_pfad,
            eintrag.morgen_uebung_datei_pfad,
            eintrag.abend_uebung_datei_pfad,
        ):
            if pfad:
                datei_loeschen(pfad)
        await session.delete(eintrag)

    freigaben_result = await session.execute(
        select(WohlbefindenFreigabe).where(WohlbefindenFreigabe.teilnehmer_id == teilnehmer_id)
    )
    for freigabe in freigaben_result.scalars().all():
        await session.delete(freigabe)

    await session.commit()


async def loesche_alle_bewerbungsdaten(session: AsyncSession, teilnehmer_id: int) -> None:
    unterlagen_result = await session.execute(
        select(Bewerbungsunterlage).where(Bewerbungsunterlage.teilnehmer_id == teilnehmer_id)
    )
    for unterlage in unterlagen_result.scalars().all():
        datei_loeschen(unterlage.speicherpfad)
        await session.delete(unterlage)
    await session.flush()

    freigaben_result = await session.execute(
        select(BewerbungsFreigabe).where(BewerbungsFreigabe.teilnehmer_id == teilnehmer_id)
    )
    for freigabe in freigaben_result.scalars().all():
        await session.delete(freigabe)
    await session.flush()

    bewerbungen_result = await session.execute(select(Bewerbung).where(Bewerbung.teilnehmer_id == teilnehmer_id))
    bewerbungen = list(bewerbungen_result.scalars().all())
    if bewerbungen:
        notizen_result = await session.execute(
            select(BewerbungsNotiz).where(BewerbungsNotiz.bewerbung_id.in_([b.id for b in bewerbungen]))
        )
        for notiz in notizen_result.scalars().all():
            await session.delete(notiz)
        await session.flush()

    for bewerbung in bewerbungen:
        await session.delete(bewerbung)

    await session.commit()


async def _loesche_karten_einer_spalte(session: AsyncSession, spalte_id: int) -> None:
    karten = list((await session.execute(select(Karte).where(Karte.spalte_id == spalte_id))).scalars().all())
    karten_ids = [k.id for k in karten]
    if not karten_ids:
        return
    for modell in (KartenZuweisung, Unteraufgabe, KartenBewegung):
        rows = list((await session.execute(select(modell).where(modell.karte_id.in_(karten_ids)))).scalars().all())
        for row in rows:
            await session.delete(row)
    await session.flush()
    for karte in karten:
        await session.delete(karte)
    await session.flush()


async def loesche_spalte_kaskadierend(session: AsyncSession, spalte_id: int) -> None:
    """Löscht eine Spalte inkl. aller ihrer Karten/Zuweisungen/
    Unteraufgaben/Bewegungen (siehe app/routers/kanban.py:spalte_loeschen).
    Löscht NICHT die Spalte selbst aus der Session - das bleibt Sache der
    aufrufenden Stelle, damit z. B. board_loeschen mehrere Spalten in einem
    Rutsch sammeln kann, bevor committed wird."""
    await _loesche_karten_einer_spalte(session, spalte_id)
    spalte = await session.get(Spalte, spalte_id)
    if spalte is not None:
        await session.delete(spalte)
    await session.flush()


async def loesche_board_kaskadierend(session: AsyncSession, board_id: int) -> None:
    """Löscht ein Team-Board vollständig: alle Spalten (inkl. Karten via
    loesche_spalte_kaskadierend) sowie die Board-Freigaben (siehe
    app/routers/kanban.py:board_loeschen)."""
    spalten_ids = list(
        (await session.execute(select(Spalte.id).where(Spalte.board_id == board_id))).scalars().all()
    )
    for spalte_id in spalten_ids:
        await _loesche_karten_einer_spalte(session, spalte_id)
        spalte = await session.get(Spalte, spalte_id)
        if spalte is not None:
            await session.delete(spalte)
    await session.flush()

    freigaben = list(
        (await session.execute(select(BoardFreigabe).where(BoardFreigabe.board_id == board_id))).scalars().all()
    )
    for freigabe in freigaben:
        await session.delete(freigabe)
    await session.flush()

    board = await session.get(Board, board_id)
    if board is not None:
        await session.delete(board)
    await session.flush()


async def loesche_teilnehmergruppe_kaskadierend(session: AsyncSession, gruppe_id: int) -> None:
    """Löscht eine Arbeitsgruppe vollständig: eigene Mitgliedschaften sowie
    Board-Freigaben, die genau dieser Gruppe gelten (BoardFreigabe.gruppe_id
    hat keine DB-seitige ON-DELETE-Regel, siehe app/models/kanban.py -
    stehen bleibende Freigaben würden sonst die Fremdschlüssel-Constraint
    verletzen). Boards selbst bleiben unberührt, nur die Freigabe an diese
    eine Gruppe fällt weg (siehe app/routers/kanban.py:gruppe_loeschen)."""
    mitglieder = list(
        (
            await session.execute(
                select(TeilnehmergruppeMitglied).where(TeilnehmergruppeMitglied.gruppe_id == gruppe_id)
            )
        )
        .scalars()
        .all()
    )
    for mitglied in mitglieder:
        await session.delete(mitglied)

    freigaben = list(
        (await session.execute(select(BoardFreigabe).where(BoardFreigabe.gruppe_id == gruppe_id))).scalars().all()
    )
    for freigabe in freigaben:
        await session.delete(freigabe)
    await session.flush()

    gruppe = await session.get(Teilnehmergruppe, gruppe_id)
    if gruppe is not None:
        await session.delete(gruppe)
    await session.commit()


async def loesche_persoenliches_kanban_board(session: AsyncSession, teilnehmer_id: int) -> None:
    """Löscht das persönliche Kanban-Board (BoardTyp.person) einer/eines
    Teilnehmer:in vollständig, inkl. aller eigenen Spalten/Karten/
    Zuweisungen/Unteraufgaben/Bewegungen - sicher als Ganzes löschbar, da ein
    Personen-Board nie für andere Teilnehmende freigegeben ist (anders als
    Team-Boards, siehe Modulkommentar oben)."""
    board_result = await session.execute(
        select(Board).where(Board.typ == BoardTyp.person, Board.person_teilnehmer_id == teilnehmer_id)
    )
    board = board_result.scalar_one_or_none()
    if board is None:
        return

    spalten_ids = list(
        (await session.execute(select(Spalte.id).where(Spalte.board_id == board.id))).scalars().all()
    )
    for spalte_id in spalten_ids:
        await loesche_spalte_kaskadierend(session, spalte_id)

    await session.delete(board)
    await session.commit()
