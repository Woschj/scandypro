"""Privates Wochen-Fortschritts-Signal für Teilnehmer:innen (siehe CLAUDE.md
Abschnitt 25 "Wohlbefinden-Trend für den Nutzer selbst" / positive
Verstärkung). Zählt Karten- und Unteraufgaben-Abschlüsse der letzten 7 Tage -
nur für die Person selbst sichtbar, nie als Vergleich oder Bewertung
dargestellt. Bewusst kein allgemeines Aktivitäts-Log, nur die zwei
schmalen Zeitstempel-Felder Karte.abgeschlossen_am / Unteraufgabe.erledigt_am.
"""

from datetime import datetime, timedelta

from sqlmodel import func, or_, select

from app.core.deps import SessionDep
from app.models.kanban import Karte, KartenZuweisung, Unteraufgabe


async def woechentliche_schritte(session: SessionDep, teilnehmer_id: int) -> int:
    """Anzahl Karten- und Unteraufgaben-Abschlüsse der/des Teilnehmer:in in
    den letzten 7 Tagen (eigene Karten oder ihr zugewiesene)."""
    seit = datetime.utcnow() - timedelta(days=7)

    zugewiesene_karten_ids = select(KartenZuweisung.karte_id).where(
        KartenZuweisung.teilnehmer_id == teilnehmer_id
    )
    karten_result = await session.execute(
        select(func.count(Karte.id)).where(
            Karte.abgeschlossen_am.is_not(None),
            Karte.abgeschlossen_am >= seit,
            or_(Karte.ersteller_id == teilnehmer_id, Karte.id.in_(zugewiesene_karten_ids)),
        )
    )
    karten_anzahl = karten_result.scalar_one()

    unteraufgaben_result = await session.execute(
        select(func.count(Unteraufgabe.id))
        .join(Karte, Unteraufgabe.karte_id == Karte.id)
        .where(
            Unteraufgabe.erledigt_am.is_not(None),
            Unteraufgabe.erledigt_am >= seit,
            or_(Unteraufgabe.zugewiesen_an == teilnehmer_id, Karte.ersteller_id == teilnehmer_id),
        )
    )
    unteraufgaben_anzahl = unteraufgaben_result.scalar_one()

    return karten_anzahl + unteraufgaben_anzahl
