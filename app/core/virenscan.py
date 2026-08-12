"""Virenprüfung hochgeladener Dateien über ClamAV (siehe
tasks/produktivreife, PR-003).

Warum das hier nötig ist: Bewerbungsunterlagen wandern zwischen Personen.
Eine Teilnehmer:in lädt ein PDF hoch, die zuständige Berufstrainer:in lädt
es herunter und öffnet es auf ihrem Arbeitsplatzrechner. Die vorhandene
Prüfung in app/core/uploads.py stellt über Endung, Größe und Magic Bytes
sicher, *dass* die Datei ein PDF/Word/Bild ist - nicht, dass ihr Inhalt
harmlos ist. Ohne Scan ist ScandyPro damit ein Verbreitungsweg innerhalb
der Einrichtung.

Angebunden wird clamd direkt über sein INSTREAM-Protokoll (asyncio-Socket,
keine zusätzliche Abhängigkeit): Das Protokoll besteht aus einer Handvoll
Zeilen, und die verfügbaren Python-Pakete dafür sind synchron - in einer
async-Anwendung würde das den Event-Loop blockieren.

Verhalten (bewusst so gewählt):
- `CLAMAV_HOST` nicht gesetzt  -> Prüfung ist aus. Das ist der
  Prototyp-Standard und in README/docs als offene Lücke dokumentiert.
- `CLAMAV_HOST` gesetzt        -> Prüfung ist verbindlich. Ist der Scanner
  nicht erreichbar oder antwortet er nicht rechtzeitig, wird der Upload
  **abgelehnt**, nicht durchgewinkt. Wer einen Scanner konfiguriert hat,
  erwartet, dass gescannt wird; ein stilles Überspringen wäre die
  gefährlichste Variante, weil sie sich wie Schutz anfühlt.
"""

import asyncio
import logging

from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

# clamd lehnt Streams oberhalb seiner StreamMaxLength ab; 25 MB liegt
# komfortabel über unserem eigenen Upload-Limit von 10 MB.
_CHUNK_GROESSE = 64 * 1024

# Nutzerseitige Meldung bewusst neutral gehalten: Sie erscheint Menschen in
# beruflicher Reha, die in aller Regel nichts falsch gemacht haben, sondern
# eine Datei aus fremder Quelle weiterreichen (siehe CLAUDE.md Abschnitt 24,
# "keine Leistungsbegriffe", "sanfte Sprache"). Keine Schuldzuweisung, kein
# Warndreieck, dafür ein klarer nächster Schritt.
_MELDUNG_FUND = (
    "Diese Datei konnte nicht gespeichert werden, weil die Sicherheitsprüfung "
    "angeschlagen hat. Das muss nichts mit dir zu tun haben - oft liegt es an "
    "der Quelle der Datei. Bitte erstelle sie neu oder wende dich an deine "
    "Ansprechperson."
)
_MELDUNG_NICHT_ERREICHBAR = (
    "Die Datei konnte gerade nicht geprüft werden und wurde deshalb nicht "
    "gespeichert. Bitte versuche es später noch einmal oder wende dich an die "
    "Verwaltung."
)


def virenscan_aktiv() -> bool:
    return bool(settings.clamav_host)


async def _frage_clamd(inhalt: bytes) -> str:
    """Schickt den Inhalt per INSTREAM an clamd und gibt dessen Antwort zurück.

    INSTREAM erwartet nach dem Kommando beliebig viele Blöcke aus
    4-Byte-Länge (big endian) + Daten, abgeschlossen von einer Länge 0.
    """
    leser, schreiber = await asyncio.open_connection(settings.clamav_host, settings.clamav_port)
    try:
        schreiber.write(b"zINSTREAM\0")
        for start in range(0, len(inhalt), _CHUNK_GROESSE):
            block = inhalt[start : start + _CHUNK_GROESSE]
            schreiber.write(len(block).to_bytes(4, "big") + block)
        schreiber.write((0).to_bytes(4, "big"))
        await schreiber.drain()

        antwort = await leser.read(4096)
        return antwort.decode("utf-8", errors="replace").strip("\0 \n\r")
    finally:
        schreiber.close()
        try:
            await schreiber.wait_closed()
        except (ConnectionError, OSError):  # Verbindung bereits weg - unkritisch
            pass


async def pruefe_auf_schadsoftware(inhalt: bytes, dateiname: str) -> None:
    """Prüft den Dateiinhalt und wirft eine HTTPException bei Fund.

    Wird von app/core/uploads.py vor dem Verschlüsseln und Schreiben
    aufgerufen - eine als schädlich erkannte Datei darf die Platte gar nicht
    erst erreichen.
    """
    if not virenscan_aktiv():
        return

    try:
        antwort = await asyncio.wait_for(_frage_clamd(inhalt), timeout=settings.clamav_timeout_sekunden)
    except (asyncio.TimeoutError, ConnectionError, OSError) as fehler:
        # Fail closed: lieber ein abgelehnter Upload als eine ungeprüfte
        # Datei, die andere Menschen später öffnen.
        logger.error(
            "Virenscanner nicht erreichbar (%s:%s) - Upload abgelehnt: %s",
            settings.clamav_host,
            settings.clamav_port,
            fehler,
        )
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _MELDUNG_NICHT_ERREICHBAR) from fehler

    if antwort.endswith("OK") and "FOUND" not in antwort:
        return

    if antwort.endswith("FOUND"):
        # Nur die Signatur protokollieren, nicht den Dateinamen: der kann
        # personenbezogen sein ("Lebenslauf Maria Muster.pdf"), und
        # Audit-/Fehlerlogs bleiben laut CLAUDE.md Abschnitt 13 frei von
        # sensiblen Inhalten.
        signatur = antwort.rsplit(" ", 1)[0].split(": ", 1)[-1]
        logger.warning("Upload wegen Virenfund abgelehnt (Signatur: %s)", signatur)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _MELDUNG_FUND)

    logger.error("Unerwartete Antwort des Virenscanners: %r", antwort)
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _MELDUNG_NICHT_ERREICHBAR)
