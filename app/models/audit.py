from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class AuditAktion(str, Enum):
    wohlbefinden_gelesen = "wohlbefinden_gelesen"
    bewerbung_gelesen = "bewerbung_gelesen"


class AuditZieltyp(str, Enum):
    wohlbefinden = "wohlbefinden"
    bewerbung = "bewerbung"


class AuditLogEintrag(SQLModel, table=True):
    """Protokolliert Fremdzugriffe auf sensible Daten (siehe
    DATENSCHUTZ_UND_BERECHTIGUNGEN.md §4.3) - ausschließlich Metadaten,
    niemals Inhalte der Wohlbefinden-/Bewerbungsdaten selbst.

    `ziel_teilnehmer_id` bleibt bewusst ohne Foreign-Key-Constraint, damit
    ein Audit-Log-Eintrag auch nach Löschung des Teilnehmer-Kontos noch als
    pseudonymisierter Nachweis (nur die ID, keine Inhalte) bestehen bleiben
    kann, statt per Kaskade mitgelöscht zu werden.
    """

    id: int | None = Field(default=None, primary_key=True)
    zeitpunkt: datetime = Field(default_factory=datetime.utcnow)
    akteur_id: int = Field(foreign_key="user.id", index=True)
    aktion: AuditAktion
    zieltyp: AuditZieltyp
    ziel_teilnehmer_id: int = Field(index=True)
    grundlage_freigabe_id: int | None = None
