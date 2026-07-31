"""Emoji-Skala für "Mein Tag" (1-10, siehe app/models/wohlbefinden.py).

Zwei getrennte Emoji-Reihen, damit Stimmung und Energie auf einen Blick
unterscheidbar bleiben, statt beide mit denselben Gesichtern darzustellen.
Farbverlauf für die Heatmap-Ansicht geht bewusst von --accent zu --brand
(kein Rot) - siehe CLAUDE.md, Abschnitt UX-Leitlinien ("keine roten
Warnsymbole").
"""

STIMMUNG_EMOJI = ["😭", "😢", "😟", "😕", "😐", "🙂", "😊", "😄", "😁", "🤩"]
ENERGIE_EMOJI = ["🪫", "😴", "🥱", "😑", "😌", "🙆", "🚶", "🏃", "⚡", "🚀"]

HEATMAP_FARBEN = [
    "#e8a33d",
    "#d19b40",
    "#ba9443",
    "#a48c47",
    "#8d844a",
    "#767d4d",
    "#5f7550",
    "#496d54",
    "#326657",
    "#1b5e5a",
]


def _index(wert: float | int | None) -> int | None:
    if wert is None:
        return None
    idx = round(wert) - 1
    return min(9, max(0, idx))


def stimmung_emoji(wert: float | int | None) -> str:
    idx = _index(wert)
    return STIMMUNG_EMOJI[idx] if idx is not None else "–"


def energie_emoji(wert: float | int | None) -> str:
    idx = _index(wert)
    return ENERGIE_EMOJI[idx] if idx is not None else "–"


def heatmap_farbe(wert: float | int | None) -> str | None:
    idx = _index(wert)
    return HEATMAP_FARBEN[idx] if idx is not None else None
