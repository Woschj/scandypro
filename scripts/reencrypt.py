#!/usr/bin/env python3
"""Schreibt alle verschlüsselten Bestandsdaten auf den aktuellen Schlüssel um.

Teil der Schlüsselrotation (PR-004, siehe app/core/crypto.py und
docs/BACKUP.md):

  1. Neuen Schlüssel VORNE an FIELD_ENCRYPTION_KEY anhängen (kommagetrennt)
  2. dieses Skript laufen lassen
  3. erst danach den alten Schlüssel entfernen

Aufruf:

    python scripts/reencrypt.py --pruefen   # nur zählen, nichts ändern
    python scripts/reencrypt.py             # umschreiben

Der Prüfmodus ist der wichtigere von beiden: Er beantwortet die Frage, die
vor Schritt 3 zählt - hängt noch irgendetwas am alten Schlüssel? Wer den
alten Schlüssel zu früh entfernt, macht die betroffenen Daten dauerhaft
unlesbar; ein Backup hilft dann auch nicht, weil es denselben Ciphertext
enthält.

Die zu bearbeitenden Spalten werden aus den Modellen abgeleitet (alle vom
Typ VerschluesselterText), nicht hier aufgezählt - eine Liste im Skript
würde beim nächsten neuen Feld veralten, ohne dass es jemandem auffällt.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.fernet import InvalidToken  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

import app.models  # noqa: E402,F401  (registriert alle Tabellen)
from app.core.config import settings  # noqa: E402
from app.core.crypto import (  # noqa: E402
    VerschluesselterText,
    anzahl_schluessel,
    ist_aktuell_verschluesselt,
    neu_verschluesseln,
)
from app.core.database import async_session_factory  # noqa: E402

# Wie viele UPDATEs pro Round-Trip gebuendelt werden.
BUENDEL_GROESSE = 500


def verschluesselte_spalten() -> list[tuple[str, str, object]]:
    """(Tabellenname, Spaltenname, Tabellenobjekt) für jede Fernet-Spalte."""
    gefunden = []
    for tabelle in SQLModel.metadata.sorted_tables:
        for spalte in tabelle.columns:
            if isinstance(spalte.type, VerschluesselterText):
                gefunden.append((tabelle.name, spalte.name, tabelle))
    return gefunden


async def bearbeite_datenbank(nur_pruefen: bool) -> tuple[int, int, int]:
    """Gibt (geprüft, veraltet, umgeschrieben) zurück.

    Gelesen und geschrieben wird mit rohem SQL, nicht über das ORM. Grund:
    der VerschluesselterText-TypeDecorator hängt an der Spalte und greift
    auch bei einem Core-`select()` - man bekäme also bereits
    *entschlüsselten* Klartext zurück und würde versuchen, den zu rotieren.
    Das schlägt fehl (Klartext ist kein gültiges Fernet-Token), und zwar
    still: `ist_aktuell_verschluesselt` meldete dann dauerhaft "veraltet",
    obwohl längst alles umgeschrieben wäre. Der Prüfmodus gäbe nie grünes
    Licht, und das eigentliche Umschreiben passierte nie.
    """
    geprueft = veraltet = umgeschrieben = 0

    async with async_session_factory() as session:
        quoter = session.bind.dialect.identifier_preparer.quote

        for tabellenname, spaltenname, tabelle in verschluesselte_spalten():
            pk_name = list(tabelle.primary_key.columns)[0].name
            t, s, p = quoter(tabellenname), quoter(spaltenname), quoter(pk_name)

            ergebnis = await session.execute(
                text(f"SELECT {p} AS pk, {s} AS wert FROM {t} WHERE {s} IS NOT NULL")
            )
            zu_schreiben: list[tuple] = []
            for zeile in ergebnis.all():
                geprueft += 1
                if ist_aktuell_verschluesselt(zeile.wert):
                    continue
                veraltet += 1
                if nur_pruefen:
                    continue
                try:
                    zu_schreiben.append((zeile.pk, neu_verschluesseln(zeile.wert).decode()))
                except InvalidToken:
                    print(
                        f"  !! {tabellenname}.{spaltenname} pk={zeile.pk}: "
                        "mit keinem bekannten Schlüssel lesbar - übersprungen",
                        file=sys.stderr,
                    )

            # Gebündelt statt einzeln: 44.000 Einzel-UPDATEs sind je ein
            # Round-Trip zur Datenbank und brauchen dafür über zehn Minuten -
            # eine Rotation, die scheinbar hängt, wird abgebrochen, und ein
            # halb rotierter Bestand ist genau der Zustand, den niemand will.
            anweisung = text(f"UPDATE {t} SET {s} = :wert WHERE {p} = :pk")
            for anfang in range(0, len(zu_schreiben), BUENDEL_GROESSE):
                buendel = zu_schreiben[anfang : anfang + BUENDEL_GROESSE]
                await session.execute(
                    anweisung, [{"pk": pk, "wert": wert} for pk, wert in buendel]
                )
                umgeschrieben += len(buendel)
                print(
                    f"  {tabellenname}.{spaltenname}: "
                    f"{min(anfang + BUENDEL_GROESSE, len(zu_schreiben))}/{len(zu_schreiben)}",
                    flush=True,
                )

            if not nur_pruefen and zu_schreiben:
                await session.commit()

    return geprueft, veraltet, umgeschrieben


def bearbeite_dateien(nur_pruefen: bool) -> tuple[int, int, int]:
    """Uploads (Bewerbungsunterlagen, Fotos) - liegen Fernet-verschlüsselt
    auf der Platte, siehe app/core/uploads.py."""
    geprueft = veraltet = umgeschrieben = 0
    wurzel = Path(settings.upload_dir)
    if not wurzel.is_dir():
        return 0, 0, 0

    for pfad in sorted(p for p in wurzel.rglob("*") if p.is_file()):
        # Platzhalter wie .gitkeep sind keine verschlüsselten Uploads und
        # würden sonst dauerhaft als "veraltet" gemeldet - der Prüfmodus
        # käme nie auf null und gäbe nie grünes Licht.
        if pfad.name.startswith("."):
            continue
        inhalt = pfad.read_bytes()
        geprueft += 1
        if ist_aktuell_verschluesselt(inhalt):
            continue
        veraltet += 1
        if nur_pruefen:
            continue
        try:
            neu = neu_verschluesseln(inhalt)
        except InvalidToken:
            print(f"  !! {pfad}: mit keinem bekannten Schlüssel lesbar - übersprungen", file=sys.stderr)
            continue

        # Temp-Datei + atomares Rename: ein Absturz mitten im Schreiben darf
        # keine halb überschriebene Bewerbungsunterlage hinterlassen.
        temp = pfad.with_suffix(pfad.suffix + ".neu")
        temp.write_bytes(neu)
        os.replace(temp, pfad)
        umgeschrieben += 1

    return geprueft, veraltet, umgeschrieben


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--pruefen",
        action="store_true",
        help="nur zählen, was am alten Schlüssel hängt - nichts verändern",
    )
    argumente = parser.parse_args()

    print(f"Konfigurierte Schlüssel: {anzahl_schluessel()}")
    if anzahl_schluessel() == 1 and not argumente.pruefen:
        print(
            "Nur ein Schlüssel konfiguriert - es gibt nichts zu rotieren.\n"
            "Zum Rotieren zuerst den neuen Schlüssel VORNE an FIELD_ENCRYPTION_KEY\n"
            "anhängen (kommagetrennt), dann dieses Skript erneut aufrufen."
        )
        return 0

    modus = "PRÜFMODUS - es wird nichts verändert" if argumente.pruefen else "Umschreiben"
    print(f"Modus: {modus}\n")

    print("Datenbank …")
    db_geprueft, db_veraltet, db_neu = await bearbeite_datenbank(argumente.pruefen)
    print(f"  {db_geprueft} Werte geprüft, {db_veraltet} auf altem Schlüssel, {db_neu} umgeschrieben")

    print("Dateien …")
    f_geprueft, f_veraltet, f_neu = bearbeite_dateien(argumente.pruefen)
    print(f"  {f_geprueft} Dateien geprüft, {f_veraltet} auf altem Schlüssel, {f_neu} umgeschrieben")

    offen = db_veraltet + f_veraltet
    print()
    if argumente.pruefen:
        if offen:
            print(
                f"{offen} Einträge hängen noch am alten Schlüssel.\n"
                "Den alten Schlüssel JETZT NOCH NICHT entfernen - erst dieses Skript\n"
                "ohne --pruefen laufen lassen."
            )
            return 1
        print(
            "Nichts hängt mehr am alten Schlüssel.\n"
            "Der alte Schlüssel kann aus FIELD_ENCRYPTION_KEY entfernt werden.\n"
            "Achtung: Backups, die vor der Rotation entstanden sind, brauchen ihn\n"
            "weiterhin - siehe docs/BACKUP.md."
        )
        return 0

    print(f"Fertig: {db_neu + f_neu} Einträge umgeschrieben.")
    print("Jetzt 'python scripts/reencrypt.py --pruefen' aufrufen; meldet es 0 offene")
    print("Einträge, kann der alte Schlüssel entfernt werden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
