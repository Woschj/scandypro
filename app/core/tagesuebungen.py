"""Rotation der Morgen-/Abend-Übung in "Mein Tag" (siehe
app/routers/wohlbefinden.py, tasks/ganzheitliche-verbesserungen/VB-006.md
und VB-018.md).

Anders als die reine Tages-Auswahl in app/core/atemuebungen.py (die nur die
*Stil-Variante* einer einzigen Übungsart auswählt) wählt dieses Modul den
*Übungstyp* selbst - z.B. "Atemübung" vs. "Körper-Scan" vs. "5-4-3-2-1-
Erdung".

Rotations-Ziel (Nutzer-Vorgabe): pro Tag zwei Übungen (morgens + abends),
bei fünf Arbeitstagen also zehn pro Woche - mit je zehn Einträgen pro Pool
wiederholt sich damit innerhalb von zwei Arbeitswochen keine Übung. Genau
das leistet `_rotations_index`: der Pool wird in Blöcken von `anzahl`
*Werktagen* durchlaufen, pro Block einmal deterministisch gemischt
(Fisher-Yates, geseedet aus Teilnehmer:in + Blocknummer + Namensraum).
Innerhalb eines Blocks kommt jeder Index genau einmal vor.

Wochenenden verbrauchen bewusst keinen eigenen Platz in der Rotation,
sondern zeigen weiter die Übung des vorangegangenen Freitags - sonst wäre
das Ziel "in zwei Wochen keine Wiederholung" mit zehn Einträgen
rechnerisch nicht erreichbar (14 Kalendertage > 10 Pool-Einträge).

Pool-Einträge sind bewusst nur Metadaten (Slug, Label) - die eigentliche
Speicherung des Ergebnisses passiert für neuere Typen über die generischen
`*_uebung_*`-Felder auf TagebuchEintrag (siehe app/models/wohlbefinden.py),
für die älteren Typen noch über je eigene Felder. Durchgängig gilt: kein
Scoring, keine wertende Sprache, wo immer möglich nur der Abschluss-
Zeitpunkt statt des Inhalts."""

import hashlib
import random
from datetime import date

MORGEN_POOL: list[dict] = [
    {"slug": "atemuebung", "label": "Atemübung"},
    {"slug": "koerperscan", "label": "Körper-Scan"},
    {"slug": "erdung_54321", "label": "5-4-3-2-1-Erdung"},
    {"slug": "wort_des_tages", "label": "Ein Wort für heute"},
    {"slug": "staerken_karte", "label": "Stärken-Karte"},
    {"slug": "absichts_karte", "label": "Absichts-Karte"},
    {"slug": "tagesmotto", "label": "Tagesmotto"},
    {"slug": "klarheits_kompass", "label": "Klarheits-Kompass"},
    {"slug": "gestern_loslassen", "label": "Gestern loslassen"},
    {"slug": "motivationsfoto", "label": "Motivations-Foto"},
]

ABEND_POOL: list[dict] = [
    {"slug": "zeichnung", "label": "Zeichnung"},
    {"slug": "mandala", "label": "Ausmal-Mandala"},
    {"slug": "ruhe_ort", "label": "Ruhe-Ort-Visualisierung"},
    {"slug": "gedanken_waage", "label": "Gedanken-Waage"},
    {"slug": "sorgen_loslassen", "label": "Sorgen loslassen"},
    {"slug": "dankbarkeitsfoto", "label": "Dankbarkeits-Foto-Moment"},
    {"slug": "mini_ziel", "label": "Mini-Ziel des Tages"},
    {"slug": "sternenhimmel", "label": "Sternenhimmel ausmalen"},
    {"slug": "abend_karte", "label": "Abend-Karte"},
    {"slug": "kerzen", "label": "Kerzen anzünden"},
]

# Zonen-Übungen (Silhouette/Kompass/Kerzen): (Label, Halte-Sekunden, Hinweis).
# Halte-Sekunden 0 = kein Countdown, direkt weiter.
KOERPERSCAN_ZONEN = [
    ("Kopf & Nacken", 5, "Tippe auf den Kopf und spüre kurz in Kopf und Nacken hinein."),
    ("Schultern", 5, "Jetzt die Schultern - lässt sich hier etwas lösen?"),
    ("Bauch", 5, "Spüre kurz in deinen Bauch hinein, ohne etwas verändern zu müssen."),
    ("Beine", 5, "Und die Beine - wie fühlen sie sich gerade an?"),
    ("Ankommen", 0, "Zum Schluss: einmal deinen ganzen Körper wahrnehmen."),
]

KLARHEITS_KOMPASS_ZONEN = [
    ("Kopf", 5, "Was denke ich gerade? Tippe auf den Kopf und lass den Gedanken kurz da sein."),
    ("Herz", 5, "Was fühle ich gerade? Tippe auf das Herz."),
    ("Bauch", 5, "Was spüre ich im Bauch? Tippe darauf und atme einmal ruhig."),
    ("Hände", 0, "Und was möchte ich heute tun? Tippe auf die Hände."),
]

KERZEN_ZONEN = [
    ("Erste Kerze", 5, "Tippe die erste Kerze an - der Tag darf jetzt zu Ende gehen."),
    ("Zweite Kerze", 5, "Die zweite Kerze - was heute war, darf so stehen bleiben."),
    ("Dritte Kerze", 0, "Die dritte Kerze - und jetzt wird es ruhig."),
]

WORT_DES_TAGES_OPTIONEN = [
    "müde", "hoffnungsvoll", "angespannt", "ruhig", "stolz", "unsicher",
    "dankbar", "erschöpft", "zufrieden", "nachdenklich", "erleichtert",
    "gereizt", "neugierig", "gelassen", "überfordert", "mutig", "einsam",
    "verbunden", "hoffend", "wach",
]

TAGESMOTTO_OPTIONEN = [
    "Ich darf langsam sein.",
    "Heute reicht gut genug.",
    "Ich schaffe genug.",
    "Ein Schritt nach dem anderen.",
    "Ich darf um Hilfe bitten.",
    "Pausen gehören dazu.",
    "Ich muss heute niemandem etwas beweisen.",
    "Ich bleibe freundlich mit mir.",
    "Was ich heute tue, zählt.",
    "Ich darf Fehler machen.",
    "Ich höre auf das, was ich brauche.",
    "Heute ist ein neuer Anlauf.",
]

STAERKEN_KARTEN_PROMPTS = [
    "Woran hast du heute gemerkt, dass du geduldig sein kannst?",
    "Was hast du heute geschafft, das vor einiger Zeit noch schwer war?",
    "Wofür würde dich jemand, der dich gut kennt, heute loben?",
    "Wann hast du heute eine Entscheidung getroffen, die zu dir passt?",
    "Was an dir hat dir heute geholfen, auch wenn es niemand gesehen hat?",
]

ABSICHTS_KARTEN_PROMPTS = [
    "Wie möchtest du heute durch den Tag gehen?",
    "Was soll dir heute wichtig sein, egal wie der Tag läuft?",
    "Womit möchtest du heute freundlich zu dir selbst sein?",
    "Was möchtest du heute bewusst einmal tun?",
    "Woran möchtest du dich heute erinnern, wenn es voll wird?",
]

ABEND_KARTEN_PROMPTS = [
    "Was hat dich heute zum Lächeln gebracht?",
    "Was war heute leichter als gedacht?",
    "Wer oder was hat dir heute gutgetan?",
    "Welchen kleinen Moment möchtest du dir von heute merken?",
    "Was nimmst du dir von heute mit in den morgigen Tag?",
]


def _werktag_nummer(datum: date) -> int:
    """Fortlaufende Nummer des Werktags (Mo-Fr) - Wochenenden zählen als der
    vorangegangene Freitag, verbrauchen also keinen eigenen Rotationsplatz
    (siehe Modul-Docstring)."""
    ordinal = datum.toordinal()
    # 0001-01-01 (ordinal 1) war ein Montag - daher ergibt (ordinal-1) % 7
    # direkt 0=Montag ... 6=Sonntag.
    wochentag = (ordinal - 1) % 7
    if wochentag > 4:
        ordinal -= wochentag - 4
        wochentag = 4
    return ((ordinal - 1) // 7) * 5 + wochentag


def _rotations_index(teilnehmer_id: int, datum: date, anzahl: int, namensraum: str) -> int:
    """Deterministischer Index in einen Pool, der innerhalb von `anzahl`
    aufeinanderfolgenden Werktagen jeden Wert genau einmal liefert."""
    werktag = _werktag_nummer(datum)
    block, position = divmod(werktag, anzahl)
    schluessel = f"{namensraum}:{teilnehmer_id}:{block}"
    seed = int(hashlib.sha256(schluessel.encode()).hexdigest(), 16)
    reihenfolge = list(range(anzahl))
    random.Random(seed).shuffle(reihenfolge)
    return reihenfolge[position]


def morgenuebung_des_tages(teilnehmer_id: int, datum: date) -> str:
    return MORGEN_POOL[_rotations_index(teilnehmer_id, datum, len(MORGEN_POOL), "morgenuebung")]["slug"]


def abenduebung_des_tages(teilnehmer_id: int, datum: date) -> str:
    return ABEND_POOL[_rotations_index(teilnehmer_id, datum, len(ABEND_POOL), "abenduebung")]["slug"]


def staerken_karte_des_tages(teilnehmer_id: int, datum: date) -> str:
    index = _rotations_index(teilnehmer_id, datum, len(STAERKEN_KARTEN_PROMPTS), "staerkenkarte")
    return STAERKEN_KARTEN_PROMPTS[index]


def absichts_karte_des_tages(teilnehmer_id: int, datum: date) -> str:
    index = _rotations_index(teilnehmer_id, datum, len(ABSICHTS_KARTEN_PROMPTS), "absichtskarte")
    return ABSICHTS_KARTEN_PROMPTS[index]


def abend_karte_des_tages(teilnehmer_id: int, datum: date) -> str:
    index = _rotations_index(teilnehmer_id, datum, len(ABEND_KARTEN_PROMPTS), "abendkarte")
    return ABEND_KARTEN_PROMPTS[index]


def _als_zonen(rohzonen: list[tuple[str, int, str]]) -> list[dict]:
    return [
        {"label": label, "halten_sekunden": sekunden, "hinweis": hinweis}
        for label, sekunden, hinweis in rohzonen
    ]


def koerperscan_zonen() -> list[dict]:
    """Körperregionen der Reihe nach, für die Körpersilhouette (siehe
    app/templates/wohlbefinden/uebersicht.html, app/static/js/
    tagebuch-interaktiv.js:initZonenUebungen). Jede Zone bringt ihren
    eigenen kurzen Hinweistext mit, der als jeweils aktueller Schritt unter
    der Grafik erscheint - visuell verortet statt als abstrakte Liste
    (siehe VB-018.md, Primitiv "Zone mit Halten-Timer")."""
    return _als_zonen(KOERPERSCAN_ZONEN)


def klarheits_kompass_zonen() -> list[dict]:
    """Vier Kompass-Felder (Kopf/Herz/Bauch/Hände) - dasselbe Primitiv wie
    der Körper-Scan, nur mit anderer Grafik und anderen Fragen."""
    return _als_zonen(KLARHEITS_KOMPASS_ZONEN)


def kerzen_zonen() -> list[dict]:
    """Drei Kerzen zum "Anzünden" als Abendritual - dasselbe Primitiv wie
    der Körper-Scan."""
    return _als_zonen(KERZEN_ZONEN)
