"""Pool an Verbinde-die-Punkte-Atemübungen fürs 5-Minuten-Tagebuch (siehe
app/routers/wohlbefinden.py, app/static/js/tagebuch-interaktiv.js).

Wie die Impuls-Pools in app/core/tagebuch_prompts.py wird täglich genau
eine Übung deterministisch aus Teilnehmer:in + Datum ausgewählt - am
selben Tag immer dieselbe, ohne dass sie separat gespeichert werden müsste
(der tatsächlich gezeigte Name wird trotzdem mitgespeichert, siehe
TagebuchEintrag.atemuebung_name, damit er bei erneutem Aufruf stabil
bleibt, auch falls der Pool hier später erweitert/umsortiert wird).

Jede Übung ist eine Folge von Punkten (Label, Halte-Sekunden - 0 bedeutet
"kein Halten, einfach weiterziehen"). "Halten"-Punkte bekommen im UI einen
kurzen, sinnvollen Timer (5-6 Sekunden) statt sofort weiterzuschalten."""

import hashlib
from datetime import date

from app.core.punkte_layout import punkte_layout

ATEMUEBUNGEN_POOL: list[dict] = [
    {"name": "Box-Atmung", "schritte": [("Einatmen", 0), ("Halten", 5), ("Ausatmen", 0), ("Halten", 5)]},
    {"name": "Ruhige Atmung", "schritte": [("Einatmen", 0), ("Ausatmen", 0), ("Einatmen", 0), ("Ausatmen", 0)]},
    {"name": "Dreieck-Atmung", "schritte": [("Einatmen", 0), ("Halten", 6), ("Ausatmen", 0)]},
    {"name": "Sanftes Ankommen", "schritte": [("Ankommen", 0), ("Einatmen", 0), ("Ausatmen", 0)]},
    {
        "name": "Fünfeck der Ruhe",
        "schritte": [("Einatmen", 0), ("Halten", 5), ("Ausatmen", 0), ("Halten", 5), ("Einatmen", 0)],
    },
    {"name": "Kurze Pause", "schritte": [("Einatmen", 0), ("Halten", 6), ("Ausatmen", 0), ("Pause", 0)]},
    {
        "name": "Sechseck-Atmung",
        "schritte": [
            ("Einatmen", 0),
            ("Halten", 5),
            ("Ausatmen", 0),
            ("Halten", 5),
            ("Einatmen", 0),
            ("Ausatmen", 0),
        ],
    },
    {
        "name": "Wellen-Atmung",
        "schritte": [("Einatmen", 0), ("Ausatmen", 0), ("Einatmen", 0), ("Ausatmen", 0), ("Einatmen", 0)],
    },
    {"name": "Anker setzen", "schritte": [("Ankommen", 0), ("Halten", 5), ("Loslassen", 0)]},
    {"name": "Vier Ecken", "schritte": [("Einatmen", 0), ("Halten", 5), ("Ausatmen", 0), ("Halten", 6)]},
    {
        "name": "Ruhepuls",
        "schritte": [("Einatmen", 0), ("Halten", 6), ("Ausatmen", 0), ("Halten", 6), ("Ausatmen", 0)],
    },
    {"name": "Klarer Moment", "schritte": [("Wahrnehmen", 0), ("Halten", 5), ("Loslassen", 0)]},
    {
        "name": "Weiter Atem",
        "schritte": [("Einatmen", 0), ("Ausatmen", 0), ("Halten", 5), ("Einatmen", 0), ("Ausatmen", 0)],
    },
    {"name": "Zwei Atemzüge", "schritte": [("Einatmen", 0), ("Halten", 5), ("Ausatmen", 0), ("Einatmen", 0)]},
    {"name": "Stiller Moment", "schritte": [("Ankommen", 0), ("Halten", 6), ("Ausatmen", 0)]},
]

_NAME_ZU_UEBUNG = {u["name"]: u for u in ATEMUEBUNGEN_POOL}


def _tages_index(teilnehmer_id: int, datum: date, anzahl: int) -> int:
    schluessel = f"atemuebung:{teilnehmer_id}:{datum.isoformat()}"
    digest = hashlib.sha256(schluessel.encode()).hexdigest()
    return int(digest, 16) % anzahl


def atemuebung_des_tages(teilnehmer_id: int, datum: date) -> str:
    return ATEMUEBUNGEN_POOL[_tages_index(teilnehmer_id, datum, len(ATEMUEBUNGEN_POOL))]["name"]


def atemuebung_punkte(name: str) -> list[dict]:
    """Layout der Punkte einer Übung als gleichmäßiges Vieleck (Anzahl
    ergibt sich aus der jeweiligen Schrittfolge) - Positionen werden hier
    berechnet statt im Template, da Jinja keine Trigonometrie kann.
    Fällt auf die erste Übung im Pool zurück, falls der gespeicherte Name
    nicht mehr existiert (z.B. nach einer Pool-Änderung)."""
    uebung = _NAME_ZU_UEBUNG.get(name, ATEMUEBUNGEN_POOL[0])
    return punkte_layout(uebung["schritte"])
