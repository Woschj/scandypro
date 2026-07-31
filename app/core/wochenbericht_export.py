"""Word-Export von Wochenberichten in die von der Einrichtung genutzte
Papierform (app/assets/wochenbericht_vorlage.docx).

Die Vorlage enthält docxtpl/Jinja2-Platzhalter ({{ kw }}, {{ name }},
{{ montag_tasks }}, {{ montag_datum }}, {{ montag_hours }}, ...) - Layout
und Feldnamen sind extern durch die Einrichtung vorgegeben, hier wird nur
befüllt, nicht das Layout gepflegt.
"""

import io
from datetime import datetime
from pathlib import Path

from docxtpl import DocxTemplate

from app.models.wochenbericht import WOCHENTAGE, Wochenbericht

VORLAGE_PFAD = Path(__file__).resolve().parent.parent / "assets" / "wochenbericht_vorlage.docx"


def _stunden_text(start: str | None, ende: str | None) -> str:
    if not start or not ende:
        return ""
    try:
        t1 = datetime.strptime(start, "%H:%M")
        t2 = datetime.strptime(ende, "%H:%M")
    except ValueError:
        return ""
    stunden = (t2 - t1).total_seconds() / 3600
    if stunden <= 0:
        return ""
    return f"{stunden:.1f}".replace(".", ",")


def wochenbericht_als_docx(bericht: Wochenbericht, teilnehmer_name: str, wochenstart) -> bytes:
    doc = DocxTemplate(VORLAGE_PFAD)
    kontext = {"kw": f"{bericht.kw_nummer}/{bericht.kw_jahr}", "name": teilnehmer_name}

    for i, tag in enumerate(WOCHENTAGE):
        eintrag = bericht.tage.get(tag, {})
        tag_datum = wochenstart.fromordinal(wochenstart.toordinal() + i)
        kontext[f"{tag}_tasks"] = eintrag.get("taetigkeiten") or ""
        kontext[f"{tag}_datum"] = tag_datum.strftime("%d.%m.%Y")
        kontext[f"{tag}_hours"] = _stunden_text(eintrag.get("start"), eintrag.get("ende"))

    doc.render(kontext)
    puffer = io.BytesIO()
    doc.save(puffer)
    return puffer.getvalue()
