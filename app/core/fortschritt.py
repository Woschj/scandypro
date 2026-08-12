"""Privates Wochen-Fortschritts-Signal für Teilnehmer:innen (siehe CLAUDE.md
Abschnitt 25 "Wohlbefinden-Trend für den Nutzer selbst" / positive
Verstärkung). Zählt jede Karte, die die Person diese Woche mindestens einen
Schritt weitergezogen hat (nicht erst bei vollständigem Abschluss - siehe
app/models/kanban.py:KartenBewegung), plus abgeschlossene Unteraufgaben.
Nur für die Person selbst sichtbar, nie als Vergleich oder Bewertung
dargestellt. Bewusst kein allgemeines Aktivitäts-Log, nur dieses eine
zweckgebundene Signal.
"""

from datetime import date, timedelta

from sqlmodel import func, or_, select

from app.core.deps import SessionDep
from app.core.zeit import jetzt
from app.models.kanban import Karte, KartenBewegung, Unteraufgabe
from app.models.wohlbefinden import TagebuchEintrag


async def woechentliche_schritte(session: SessionDep, teilnehmer_id: int) -> int:
    """Anzahl Karten, die die Person in den letzten 7 Tagen mindestens einen
    Schritt weitergezogen hat (jede Karte zählt nur einmal, egal wie oft sie
    bewegt wurde), plus abgeschlossene Unteraufgaben."""
    seit = jetzt() - timedelta(days=7)

    bewegte_karten_result = await session.execute(
        select(func.count(func.distinct(KartenBewegung.karte_id))).where(
            KartenBewegung.bewegt_von_id == teilnehmer_id,
            KartenBewegung.bewegt_am >= seit,
        )
    )
    bewegte_karten_anzahl = bewegte_karten_result.scalar_one()

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

    return bewegte_karten_anzahl + unteraufgaben_anzahl


async def woechentliche_tagebuch_tage(session: SessionDep, teilnehmer_id: int) -> int:
    """Anzahl Tage in den letzten 7 Tagen, an denen die Person mindestens
    einen Teil des 5-Minuten-Tagebuchs (morgens oder abends) ausgefüllt hat
    - siehe app/models/wohlbefinden.py:TagebuchEintrag.

    Bewusst eine reine Teilnahme-Zählung statt einer Stimmungs-Auswertung:
    das Schreiben selbst ist der Erfolg, unabhängig vom Inhalt - so kann
    dieses Signal nie negativ ausfallen, selbst an einem inhaltlich
    schweren Tag (siehe CLAUDE.md "keine roten Warnsymbole")."""
    seit = date.today() - timedelta(days=6)

    result = await session.execute(
        select(func.count(func.distinct(TagebuchEintrag.datum))).where(
            TagebuchEintrag.teilnehmer_id == teilnehmer_id,
            TagebuchEintrag.datum >= seit,
            or_(TagebuchEintrag.morgen_ausgefuellt_am.is_not(None), TagebuchEintrag.abend_ausgefuellt_am.is_not(None)),
        )
    )
    return result.scalar_one()
