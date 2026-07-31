from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

WOCHENTAGE = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag"]
WOCHENTAG_LABELS = {
    "montag": "Montag",
    "dienstag": "Dienstag",
    "mittwoch": "Mittwoch",
    "donnerstag": "Donnerstag",
    "freitag": "Freitag",
}


class WochenberichtStatus(str, Enum):
    entwurf = "entwurf"
    abgegeben = "abgegeben"


class Wochenbericht(SQLModel, table=True):
    """Wöchentlicher Tätigkeitsbericht eines Teilnehmers, mit einem Eintrag
    pro Werktag (angelehnt an das Wochenbericht/Timesheet-Konzept aus
    Scandy2: je Tag Start-/Endzeit + Tätigkeiten).

    `tage` ist ein JSON-Objekt mit den Schlüsseln aus WOCHENTAGE, Werte je
    `{"start": "08:00"|None, "ende": "16:00"|None, "taetigkeiten": str|None}`.
    Ein JSON-Feld statt 15 Einzelspalten, weil die Struktur nur innerhalb
    dieses einen Wochenberichts gebraucht wird und nie einzeln über Tage
    hinweg abgefragt werden muss.

    Sichtbar für Berufstrainer nur im Status "abgegeben" und nur, wenn sie
    ein Handlungsfeld leiten, dessen Teilnehmergruppe die/der Teilnehmer:in
    angehört (siehe app/core/access.py).
    """

    id: int | None = Field(default=None, primary_key=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)
    kw_jahr: int
    kw_nummer: int = Field(ge=1, le=53)
    tage: dict = Field(sa_column=Column(JSON))
    besonderheiten: str | None = None
    status: WochenberichtStatus = WochenberichtStatus.entwurf
    abgegeben_am: datetime | None = None
    erstellt_am: datetime = Field(default_factory=datetime.utcnow)


def leere_tage() -> dict:
    return {tag: {"start": None, "ende": None, "taetigkeiten": None} for tag in WOCHENTAGE}
