"""Geteilte Geometrie für die "Punkte verbinden"-Übungswidgets in "Mein Tag"
(Atemübung, Körper-Scan) - berechnet ein gleichmäßiges Vieleck aus einer
Schrittfolge (Label, Halte-Sekunden), siehe app/core/atemuebungen.py,
app/core/tagesuebungen.py, app/static/js/tagebuch-interaktiv.js.

Ausgelagert, damit beide Übungen exakt dasselbe SVG-/Timer-Verhalten teilen,
statt die Trigonometrie zweimal zu pflegen."""

import math


def punkte_layout(schritte: list[tuple[str, int]]) -> list[dict]:
    anzahl = len(schritte)
    mittel_x, mittel_y, radius = 120, 110, 80

    punkte = []
    for i, (label, halten_sekunden) in enumerate(schritte):
        winkel = -math.pi / 2 + (2 * math.pi * i / anzahl)
        punkte.append(
            {
                "cx": round(mittel_x + radius * math.cos(winkel), 1),
                "cy": round(mittel_y + radius * math.sin(winkel), 1),
                "label": label,
                "halten_sekunden": halten_sekunden,
            }
        )
    return punkte
