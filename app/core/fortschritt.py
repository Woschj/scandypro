"""Privates Wochen-Fortschritts-Signal für Teilnehmer:innen (siehe CLAUDE.md
Abschnitt 25 "Wohlbefinden-Trend für den Nutzer selbst" / positive
Verstärkung). Zählt jede Karte, die die Person diese Woche mindestens einen
Schritt weitergezogen hat (nicht erst bei vollständigem Abschluss - siehe
app/models/kanban.py:KartenBewegung), plus abgeschlossene Unteraufgaben.
Nur für die Person selbst sichtbar, nie als Vergleich oder Bewertung
dargestellt. Bewusst kein allgemeines Aktivitäts-Log, nur dieses eine
zweckgebundene Signal.
"""

from datetime import date, datetime, timedelta

from sqlmodel import func, or_, select

from app.core.deps import SessionDep
from app.core.skala import stimmung_emoji
from app.core.skala import trend as _trend
from app.models.kanban import Karte, KartenBewegung, Unteraufgabe
from app.models.wohlbefinden import WohlbefindenEintrag


async def woechentliche_schritte(session: SessionDep, teilnehmer_id: int) -> int:
    """Anzahl Karten, die die Person in den letzten 7 Tagen mindestens einen
    Schritt weitergezogen hat (jede Karte zählt nur einmal, egal wie oft sie
    bewegt wurde), plus abgeschlossene Unteraufgaben."""
    seit = datetime.utcnow() - timedelta(days=7)

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


def _wochenstart(bezugsdatum: date) -> date:
    return bezugsdatum - timedelta(days=bezugsdatum.weekday())


async def woechentliche_stimmung(session: SessionDep, teilnehmer_id: int) -> dict | None:
    """Kompakte Stimmungs-Zusammenfassung fürs Dashboard (Emoji + Trend-Pfeil
    gegenüber der Vorwoche) - bewusst nur Stimmung, nicht die volle
    Auswertung aus app/routers/wohlbefinden.py (Energie, Heatmap): das
    Dashboard soll auf einen Blick lesbar bleiben, Details bleiben "Mein Tag"
    vorbehalten. `None`, wenn diese Woche noch kein Eintrag existiert - dann
    zeigt das Dashboard bewusst gar nichts statt einer leeren/wertenden
    Anzeige (siehe CLAUDE.md "keine roten Warnsymbole")."""
    heute = date.today()
    start = _wochenstart(heute)
    tage_diese_woche = [start + timedelta(days=i) for i in range(7)]
    tage_vorwoche = [start - timedelta(days=7 - i) for i in range(7)]

    diese_woche_result = await session.execute(
        select(WohlbefindenEintrag.stimmung).where(
            WohlbefindenEintrag.teilnehmer_id == teilnehmer_id,
            WohlbefindenEintrag.datum.in_(tage_diese_woche),
        )
    )
    werte_diese_woche = list(diese_woche_result.scalars().all())
    if not werte_diese_woche:
        return None

    vorwoche_result = await session.execute(
        select(WohlbefindenEintrag.stimmung).where(
            WohlbefindenEintrag.teilnehmer_id == teilnehmer_id,
            WohlbefindenEintrag.datum.in_(tage_vorwoche),
        )
    )
    werte_vorwoche = list(vorwoche_result.scalars().all())

    avg_diese_woche = sum(werte_diese_woche) / len(werte_diese_woche)
    avg_vorwoche = sum(werte_vorwoche) / len(werte_vorwoche) if werte_vorwoche else None

    return {
        "emoji": stimmung_emoji(avg_diese_woche),
        "trend": _trend(avg_diese_woche, avg_vorwoche),
    }
