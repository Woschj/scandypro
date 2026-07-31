"""Führt Bewerbungsunterlagen (Anschreiben, Lebenslauf, Zeugnisse) zu einem
PDF zusammen.

Nur PDF- und Bilddateien lassen sich ohne externe Konvertierungssoftware
(z.B. LibreOffice, hier bewusst nicht als Abhängigkeit eingeführt)
verlustfrei einbetten. Word-Dokumente werden übersprungen und der
aufrufende Code informiert darüber, statt sie stillschweigend wegzulassen.

Arbeitet mit bereits entschlüsselten Bytes (siehe
app/core/uploads.py:datei_lesen_entschluesselt) statt Dateipfaden, da die
Unterlagen verschlüsselt auf der Platte liegen.
"""

import io
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter

BILD_ENDUNGEN = {".jpg", ".jpeg", ".png"}


def _bild_als_pdf_seite(daten: bytes) -> io.BytesIO:
    bild = Image.open(io.BytesIO(daten))
    if bild.mode != "RGB":
        bild = bild.convert("RGB")
    puffer = io.BytesIO()
    bild.save(puffer, format="PDF")
    puffer.seek(0)
    return puffer


def unterlagen_zu_pdf(dateien: list[tuple[str, bytes]]) -> tuple[bytes, list[str]]:
    """dateien: Liste aus (original_dateiname, entschlüsselter Inhalt).

    Returns (zusammengeführtes PDF, Liste nicht eingebundener Dateinamen).
    """
    writer = PdfWriter()
    uebersprungen: list[str] = []

    for name, inhalt in dateien:
        endung = Path(name).suffix.lower()
        try:
            if endung == ".pdf":
                for seite in PdfReader(io.BytesIO(inhalt)).pages:
                    writer.add_page(seite)
            elif endung in BILD_ENDUNGEN:
                for seite in PdfReader(_bild_als_pdf_seite(inhalt)).pages:
                    writer.add_page(seite)
            else:
                uebersprungen.append(name)
        except Exception:
            uebersprungen.append(name)

    puffer = io.BytesIO()
    writer.write(puffer)
    return puffer.getvalue(), uebersprungen
