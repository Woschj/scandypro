from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class RoleEnum(str, Enum):
    teilnehmer = "teilnehmer"
    berufstrainer = "berufstrainer"
    psychosoziale_mitarbeit = "psychosoziale_mitarbeit"
    einrichtungs_admin = "einrichtungs_admin"


class User(SQLModel, table=True):
    """Prototyp-Vereinfachung: genau eine Rolle pro Account.

    Das Konzept (siehe docs/DATENSCHUTZ_UND_BERECHTIGUNGEN.md) erlaubt
    mehrere Rollen pro Person; für den Bewertungs-Prototyp reicht ein
    einzelnes Feld, um die Berechtigungsmatrix klickbar zu machen.
    """

    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: RoleEnum
    abteilung_id: int | None = Field(default=None, foreign_key="abteilung.id")
    # Deaktivierte Accounts können sich nicht mehr einloggen, bleiben aber
    # mit allen Daten erhalten und sind reaktivierbar - Zwischenstufe
    # zwischen "aktiv" und Löschung (siehe app/routers/admin.py).
    aktiv: bool = True
    letzter_login: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
