"""Impuls-Pools für das 5-Minuten-Tagebuch ("Mein Tag", siehe
app/models/wohlbefinden.py:TagebuchEintrag).

Jeder Tag zeigt neben dem festen Kernimpuls (morgens: Dankbarkeit, abends:
großartige Dinge) genau einen zusätzlichen, rotierenden Impuls - deterministisch
aus Teilnehmer:in + Datum abgeleitet, damit derselbe Tag beim erneuten Aufruf
immer denselben Impuls zeigt, ohne ihn extra speichern zu müssen (die
tatsächlich gestellte Frage wird trotzdem mit der Antwort gespeichert, siehe
TagebuchEintrag.morgen_impuls_frage/abend_impuls_frage - so bleibt sie auch
stabil, falls der Pool hier später erweitert/umsortiert wird).

Quelle: Klarheit- und Vorsätze-Impulse fürs Morgen-Slot, Abendreflexion-
Impulse fürs Abend-Slot (Nutzer-Vorgabe).
"""

import hashlib
from datetime import date

MORGEN_IMPULSE = [
    # Klarheit
    "Was ist das Wichtigste, das ich heute tun könnte?",
    "Wovor weiche ich aus, das meine Aufmerksamkeit verdient?",
    "Wenn ich diese Woche nur eine Sache erreichen könnte, welche wäre das?",
    "Was raubt mir gerade jetzt Energie?",
    "Welche Entscheidung würde mein Leben vereinfachen?",
    "Wo verkompliziere ich Dinge?",
    "Was würde mein fokussiertestes Selbst heute priorisieren?",
    "Was kann ich streichen oder delegieren?",
    "Was ist der nächste Schritt bei meinem wichtigsten Projekt?",
    "Was würde ich bereuen, heute nicht getan zu haben?",
    # Vorsätze
    "Wie möchte ich mich am Ende des heutigen Tages fühlen?",
    "Welche Eigenschaft möchte ich heute in meine Begegnungen einbringen?",
    "Welche Grenze muss ich heute wahren?",
    "Welche Gewohnheit möchte ich heute üben?",
    "Wie kann ich besser für jemanden da sein, den ich liebe?",
    "Wie würde Mut heute aussehen?",
    "Welche Wahrheit muss ich aussprechen?",
    "Woran möchte ich mich erinnern, wenn der heutige Tag schwierig wird?",
    "Was würde mein bestes Selbst heute Morgen als Erstes tun?",
    "Welcher Vorsatz, würde ich ihn ehren, würde meinen Tag verwandeln?",
]

ABEND_IMPULSE = [
    "Was war der schönste Moment des heutigen Tages?",
    "Was hat mich herausgefordert, und wie habe ich reagiert?",
    "Was habe ich heute gelernt?",
    "Was hätte ich besser machen können?",
    "Worauf bin ich vom heutigen Tag stolz?",
    "Auf wen hatte ich einen positiven Einfluss?",
    "Was möchte ich morgen anders machen?",
    "Was trage ich in den Schlaf mit, das ich loslassen könnte?",
    "Was würde dazu führen, dass sich morgen erfolgreich anfühlt?",
    "Wie bin ich heute gewachsen, sei es auch nur ein wenig?",
]


def _tages_index(teilnehmer_id: int, datum: date, anzahl: int) -> int:
    schluessel = f"{teilnehmer_id}:{datum.isoformat()}"
    digest = hashlib.sha256(schluessel.encode()).hexdigest()
    return int(digest, 16) % anzahl


def morgen_impuls_des_tages(teilnehmer_id: int, datum: date) -> str:
    return MORGEN_IMPULSE[_tages_index(teilnehmer_id, datum, len(MORGEN_IMPULSE))]


def abend_impuls_des_tages(teilnehmer_id: int, datum: date) -> str:
    return ABEND_IMPULSE[_tages_index(teilnehmer_id, datum, len(ABEND_IMPULSE))]
