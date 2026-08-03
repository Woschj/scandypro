"""Wöchentliche Rotation der Morgen-/Abend-Übung in "Mein Tag" (siehe
app/routers/wohlbefinden.py, tasks/ganzheitliche-verbesserungen/VB-006.md).

Anders als die reine Tages-Auswahl in app/core/atemuebungen.py (die nur die
*Stil-Variante* einer einzigen Übungsart auswählt) wählt dieses Modul den
*Übungstyp* selbst - z.B. "Atemübung" vs. "Körper-Scan" vs. "5-4-3-2-1-
Erdung". Damit innerhalb einer Arbeitswoche (Mo-Fr) kein Typ doppelt gezeigt
wird, wird pro Kalenderwoche eine deterministische Permutation des Pools
gezogen (Fisher-Yates, geseedet aus Teilnehmer:in + ISO-Woche + Namensraum)
statt wie bei den Atemübungs-Varianten nur ein einzelner Tages-Hash - ein
einzelner Tages-Hash garantiert Stabilität pro Tag, aber keine Verteilung
über mehrere Tage hinweg.

Pool-Einträge sind bewusst nur Metadaten (Slug, Label, ggf. statische
Inhalte) - die eigentliche Speicherung des Ergebnisses bleibt pro Typ ein
eigenes, schmales Feld auf TagebuchEintrag (siehe app/models/wohlbefinden.py),
analog zum bestehenden Atemübungs-/Zeichnungs-Muster: kein Scoring, keine
wertende Sprache, wo immer möglich nur der Abschluss-Zeitpunkt statt des
Inhalts gespeichert."""

import hashlib
import random
from datetime import date

MORGEN_POOL: list[dict] = [
    {"slug": "atemuebung", "label": "Atemübung"},
    {"slug": "koerperscan", "label": "Körper-Scan"},
    {"slug": "erdung_54321", "label": "5-4-3-2-1-Erdung"},
    {"slug": "wort_des_tages", "label": "Ein Wort für heute"},
    {"slug": "staerken_karte", "label": "Stärken-Karte"},
]

ABEND_POOL: list[dict] = [
    {"slug": "zeichnung", "label": "Zeichnung"},
    {"slug": "mandala", "label": "Ausmal-Mandala"},
    {"slug": "ruhe_ort", "label": "Ruhe-Ort-Visualisierung"},
    {"slug": "gedanken_waage", "label": "Gedanken-Waage"},
    {"slug": "sorgen_loslassen", "label": "Sorgen loslassen"},
    {"slug": "dankbarkeitsfoto", "label": "Dankbarkeits-Foto-Moment"},
    {"slug": "mini_ziel", "label": "Mini-Ziel des Tages"},
]

KOERPERSCAN_ZONEN = [
    ("Kopf & Nacken", 5),
    ("Schultern", 5),
    ("Bauch", 5),
    ("Beine", 5),
    ("Ankommen", 0),
]

WORT_DES_TAGES_OPTIONEN = [
    "müde", "hoffnungsvoll", "angespannt", "ruhig", "stolz", "unsicher",
    "dankbar", "erschöpft", "zufrieden", "nachdenklich", "erleichtert",
    "gereizt", "neugierig", "gelassen", "überfordert", "mutig", "einsam",
    "verbunden", "hoffend", "wach",
]

STAERKEN_KARTEN_PROMPTS = [
    "Woran hast du heute gemerkt, dass du geduldig sein kannst?",
    "Was hast du heute geschafft, das vor einiger Zeit noch schwer war?",
    "Wofür würde dich jemand, der dich gut kennt, heute loben?",
    "Wann hast du heute eine Entscheidung getroffen, die zu dir passt?",
    "Was an dir hat dir heute geholfen, auch wenn es niemand gesehen hat?",
]


def _woechentlicher_index(teilnehmer_id: int, datum: date, anzahl: int, namensraum: str) -> int:
    iso_jahr, iso_woche, iso_wochentag = datum.isocalendar()
    schluessel = f"{namensraum}:{teilnehmer_id}:{iso_jahr}:{iso_woche}"
    seed = int(hashlib.sha256(schluessel.encode()).hexdigest(), 16)
    reihenfolge = list(range(anzahl))
    random.Random(seed).shuffle(reihenfolge)
    position = (iso_wochentag - 1) % anzahl
    return reihenfolge[position]


def morgenuebung_des_tages(teilnehmer_id: int, datum: date) -> str:
    index = _woechentlicher_index(teilnehmer_id, datum, len(MORGEN_POOL), "morgenuebung")
    return MORGEN_POOL[index]["slug"]


def abenduebung_des_tages(teilnehmer_id: int, datum: date) -> str:
    index = _woechentlicher_index(teilnehmer_id, datum, len(ABEND_POOL), "abenduebung")
    return ABEND_POOL[index]["slug"]


def staerken_karte_des_tages(teilnehmer_id: int, datum: date) -> str:
    index = _woechentlicher_index(teilnehmer_id, datum, len(STAERKEN_KARTEN_PROMPTS), "staerkenkarte")
    return STAERKEN_KARTEN_PROMPTS[index]


def koerperscan_zonen() -> list[dict]:
    """Körperregionen der Reihe nach, für das Körper-Scan-Widget (siehe
    app/templates/wohlbefinden/uebersicht.html, app/static/js/
    tagebuch-interaktiv.js:initKoerperscan). Bewusst eine eigene, lineare
    Zonen-Liste statt Wiederverwendung des Atemübungs-Punkte-Layouts
    (app/core/punkte_layout.py) - ein Vieleck aus abstrakten Punkten hat
    keinen inhaltlichen Bezug zu einem Körper-Scan; hier wandert man
    der Reihe nach eine Liste von Körperregionen durch, ohne eine Linie
    zwischen ihnen zu ziehen."""
    return [{"label": label, "halten_sekunden": sekunden} for label, sekunden in KOERPERSCAN_ZONEN]
