"""Feldweise Verschlüsselung für Art.-9-sensible Freitextfelder.

Fernet (symmetrisch, authentifiziert). Schlüssel kommen aus
settings.field_encryption_key (ENV, analog zum bestehenden SECRET_KEY-
Muster).

Schlüsselrotation (PR-004): Der Wert darf **mehrere** kommagetrennte
Schlüssel enthalten, neuester zuerst. Verschlüsselt wird immer mit dem
ersten, entschlüsselt mit jedem - das ist genau das, was `MultiFernet`
leistet. Ein einzelner Schlüssel (der Normalfall und alle bestehenden
Installationen) verhält sich damit unverändert.

Ablauf einer Rotation, siehe docs/BACKUP.md und scripts/reencrypt.py:

  1. neuen Schlüssel VORNE anhängen  -> neue Daten nutzen ihn, alte bleiben
                                        lesbar
  2. scripts/reencrypt.py            -> schreibt Bestandsdaten um
  3. alten Schlüssel entfernen       -> erst wenn Schritt 2 sauber durch ist

Wer Schritt 3 vor Schritt 2 macht, macht alle Altdaten dauerhaft unlesbar.
Deshalb hat das Skript einen Prüfmodus, der vorher meldet, ob noch etwas am
alten Schlüssel hängt.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import settings

logger = logging.getLogger(__name__)


def _schluessel_liste() -> list[str]:
    schluessel = [k.strip() for k in settings.field_encryption_key.split(",") if k.strip()]
    if not schluessel:
        raise ValueError("FIELD_ENCRYPTION_KEY ist leer - ohne Schlüssel keine Verschlüsselung.")
    return schluessel


_einzelne = [Fernet(k.encode()) for k in _schluessel_liste()]
_fernet = MultiFernet(_einzelne)

# Nur der aktuelle (erste) Schlüssel - gebraucht, um zu erkennen, ob ein
# Wert schon auf dem neuesten Stand ist (siehe ist_aktuell_verschluesselt).
_aktueller = _einzelne[0]


def anzahl_schluessel() -> int:
    return len(_einzelne)


def verschluesseln(klartext: str) -> str:
    return _fernet.encrypt(klartext.encode()).decode()


def entschluesseln(chiffretext: str) -> str:
    return _fernet.decrypt(chiffretext.encode()).decode()


def verschluessle_bytes(daten: bytes) -> bytes:
    """Für hochgeladene Dateien (Lebenslauf/Zeugnisse/Anschreiben/Deckblatt),
    siehe app/core/uploads.py. Fernet ist kein Streaming-Verfahren - bei der
    bestehenden 10-MB-Obergrenze (app/core/uploads.py) unkritisch, komplett
    im Speicher zu ver-/entschlüsseln."""
    return _fernet.encrypt(daten)


def entschluessle_bytes(daten: bytes) -> bytes:
    return _fernet.decrypt(daten)


def ist_aktuell_verschluesselt(token: str | bytes) -> bool:
    """True, wenn der Wert mit dem *ersten* Schlüssel entschlüsselbar ist.

    Grundlage für den Prüfmodus von scripts/reencrypt.py: nur so lässt sich
    vor dem Entfernen eines alten Schlüssels feststellen, ob noch Daten an
    ihm hängen.
    """
    roh = token.encode() if isinstance(token, str) else token
    try:
        _aktueller.decrypt(roh)
        return True
    except InvalidToken:
        return False


def neu_verschluesseln(token: str | bytes) -> bytes:
    """Schreibt einen Wert auf den aktuellen Schlüssel um.

    `MultiFernet.rotate` entschlüsselt mit einem beliebigen bekannten
    Schlüssel und verschlüsselt mit dem ersten - inklusive frischem
    Zeitstempel, was bei einer Rotation gewollt ist.
    """
    roh = token.encode() if isinstance(token, str) else token
    return _fernet.rotate(roh)


class VerschluesselterText(TypeDecorator):
    """Transparente Verschlüsselung auf ORM-Ebene.

    Router/Templates arbeiten weiterhin mit Klartext - in der Datenbank
    liegt ausschließlich Ciphertext. Bei falschem/fehlendem Schlüssel wird
    kein Fehler an den Client durchgereicht (siehe CLAUDE.md "Fehler-
    behandlung" - keine internen Details nach außen), sondern geloggt und
    `None` zurückgegeben.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return verschluesseln(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        try:
            return entschluesseln(value)
        except InvalidToken:
            logger.error("Konnte verschlüsseltes Feld nicht entschlüsseln (falscher Schlüssel?).")
            return None
