"""Feldweise Verschlüsselung für Art.-9-sensible Freitextfelder.

Fernet (symmetrisch, authentifiziert) - Schlüssel kommt aus
settings.field_encryption_key (ENV, analog zum bestehenden SECRET_KEY-
Muster). Kein Key-Rotation-Mechanismus in dieser Ausbaustufe (siehe
README, "Bekannte Lücken dieses Prototyps").
"""

import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import settings

logger = logging.getLogger(__name__)

_fernet = Fernet(settings.field_encryption_key.encode())


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
