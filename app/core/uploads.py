"""Sicheres Speichern von Datei-Uploads (Bewerbungsunterlagen).

Zentrale Stelle für Validierung (Endung, Größe) und Storage-Zugriff, damit
diese Regeln nicht in jedem Router einzeln dupliziert werden.
"""

import uuid
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.core.crypto import entschluessle_bytes, verschluessle_bytes

ERLAUBTE_ENDUNGEN = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"}
MAX_DATEIGROESSE_BYTES = 10 * 1024 * 1024


async def datei_speichern(upload: UploadFile, unterordner: str) -> tuple[str, str, int]:
    """Speichert einen Upload verschlüsselt auf der Platte.

    Nutzt einen zufälligen UUID-Dateinamen statt des Client-Dateinamens auf
    der Platte, um Path-Traversal-Angriffe und Namenskollisionen
    auszuschließen - der Original-Dateiname wird nur als Metadatum für
    Anzeige/Download in der DB gespeichert. Der Dateiinhalt wird vor dem
    Schreiben mit Fernet verschlüsselt (siehe app/core/crypto.py) - auf der
    Platte liegt nie Klartext.

    Returns: (original_dateiname, relativer_speicherpfad, groesse_bytes)
    groesse_bytes bezieht sich auf die unverschlüsselte Originalgröße.
    """
    endung = Path(upload.filename or "").suffix.lower()
    if endung not in ERLAUBTE_ENDUNGEN:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Dateityp {endung or '(unbekannt)'} nicht erlaubt. "
            f"Erlaubt: {', '.join(sorted(ERLAUBTE_ENDUNGEN))}.",
        )

    inhalt = bytearray()
    while chunk := await upload.read(1024 * 1024):
        inhalt.extend(chunk)
        if len(inhalt) > MAX_DATEIGROESSE_BYTES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Datei zu groß (max. 10 MB).")

    ziel_ordner = Path(settings.upload_dir) / unterordner
    ziel_ordner.mkdir(parents=True, exist_ok=True)

    dateiname = f"{uuid.uuid4().hex}{endung}"
    ziel_pfad = ziel_ordner / dateiname

    async with aiofiles.open(ziel_pfad, "wb") as f:
        await f.write(verschluessle_bytes(bytes(inhalt)))

    relativer_pfad = f"{unterordner}/{dateiname}"
    return upload.filename or dateiname, relativer_pfad, len(inhalt)


def datei_loeschen(relativer_pfad: str) -> None:
    (Path(settings.upload_dir) / relativer_pfad).unlink(missing_ok=True)


def voller_pfad(relativer_pfad: str) -> Path:
    return Path(settings.upload_dir) / relativer_pfad


async def datei_lesen_entschluesselt(relativer_pfad: str) -> bytes:
    """Liest eine gespeicherte Upload-Datei und entschlüsselt sie für Anzeige/
    Download/PDF-Zusammenführung - siehe app/routers/bewerbungen.py."""
    async with aiofiles.open(voller_pfad(relativer_pfad), "rb") as f:
        verschluesselt = await f.read()
    return entschluessle_bytes(verschluesselt)
