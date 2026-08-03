"""Selbstauskunft (Art. 15 DSGVO): baut die eigenen Wohlbefinden- und
Bewerbungsdaten einer/eines Teilnehmer:in als JSON-serialisierbares dict,
siehe app/routers/auth.py:konto_export.

Enthält nur Daten, deren Owner die anfragende Person selbst ist - kein
Fremdzugriffspfad, daher ohne zusätzliche Freigabe-Prüfung aufrufbar."""

from datetime import date

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.bewerbung import Bewerbung, BewerbungsNotiz, Bewerbungsunterlage
from app.models.wohlbefinden import TagebuchEintrag


def _iso(wert: date | None) -> str | None:
    return wert.isoformat() if wert else None


async def eigene_daten_export(session: AsyncSession, teilnehmer_id: int) -> dict:
    tagebuch_result = await session.execute(
        select(TagebuchEintrag)
        .where(TagebuchEintrag.teilnehmer_id == teilnehmer_id)
        .order_by(TagebuchEintrag.datum)
    )
    tagebuch = [
        {
            "datum": _iso(e.datum),
            "dankbarkeit": [e.dankbarkeit_1, e.dankbarkeit_2, e.dankbarkeit_3],
            "morgen_impuls_frage": e.morgen_impuls_frage,
            "morgen_impuls_antwort": e.morgen_impuls_antwort,
            "energie_level": e.energie_level,
            "atemuebung_name": e.atemuebung_name,
            "highlights": [e.highlight_1, e.highlight_2, e.highlight_3],
            "abend_impuls_frage": e.abend_impuls_frage,
            "abend_impuls_antwort": e.abend_impuls_antwort,
            "hat_zeichnung": e.zeichnung_pfad is not None,
        }
        for e in tagebuch_result.scalars().all()
    ]

    bewerbungen_result = await session.execute(
        select(Bewerbung).where(Bewerbung.teilnehmer_id == teilnehmer_id).order_by(Bewerbung.erstellt_am)
    )
    unterlagen_result = await session.execute(
        select(Bewerbungsunterlage).where(Bewerbungsunterlage.teilnehmer_id == teilnehmer_id)
    )
    unterlagen_pro_bewerbung: dict[int | None, list[str]] = {}
    for u in unterlagen_result.scalars().all():
        unterlagen_pro_bewerbung.setdefault(u.bewerbung_id, []).append(u.original_dateiname)

    notizen_result = await session.execute(
        select(BewerbungsNotiz)
        .where(BewerbungsNotiz.bewerbung_id.in_(select(Bewerbung.id).where(Bewerbung.teilnehmer_id == teilnehmer_id)))
        .order_by(BewerbungsNotiz.erstellt_am)
    )
    notizen_pro_bewerbung: dict[int, list[dict]] = {}
    for n in notizen_result.scalars().all():
        notizen_pro_bewerbung.setdefault(n.bewerbung_id, []).append(
            {"text": n.text, "erstellt_am": n.erstellt_am.isoformat()}
        )

    bewerbungen = [
        {
            "firma": b.firma,
            "position": b.position,
            "status": b.status.value,
            "beworben_am": _iso(b.beworben_am),
            "naechster_termin": _iso(b.naechster_termin),
            "notizen": notizen_pro_bewerbung.get(b.id, []),
            "unterlagen": unterlagen_pro_bewerbung.get(b.id, []),
        }
        for b in bewerbungen_result.scalars().all()
    ]

    return {
        "hinweis": "Deine eigenen Daten aus ScandyPro (Art. 15 DSGVO). Hochgeladene Dateien "
        "(Zeichnungen, Lebenslauf, Zeugnisse) sind hier nur als Dateiname aufgeführt, "
        "nicht als Anhang - lade sie bei Bedarf einzeln über die jeweilige Seite herunter.",
        "mein_tag": tagebuch,
        "bewerbungen": bewerbungen,
    }
