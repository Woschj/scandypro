from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel
from app.core.zeit import jetzt


class RoleEnum(str, Enum):
    teilnehmer = "teilnehmer"
    berufstrainer = "berufstrainer"
    psychosoziale_mitarbeit = "psychosoziale_mitarbeit"
    einrichtungs_admin = "einrichtungs_admin"


class AuthSource(str, Enum):
    """Woher ein Account seine Anmeldung bezieht - siehe app/core/oidc.py.

    `sso`-Accounts können zusätzlich (nicht stattdessen) auch ein lokales
    Passwort besitzen, falls eines gesetzt wurde; `password_hash` ist daher
    unabhängig vom auth_source immer nullable, nicht nur bei sso."""

    local = "local"
    sso = "sso"


class User(SQLModel, table=True):
    """Prototyp-Vereinfachung: genau eine Rolle pro Account.

    Das Konzept (siehe docs/DATENSCHUTZ_UND_BERECHTIGUNGEN.md) erlaubt
    mehrere Rollen pro Person; für den Bewertungs-Prototyp reicht ein
    einzelnes Feld, um die Berechtigungsmatrix klickbar zu machen.

    `role` ist nullable, weil ein per SSO neu angelegter Account zunächst
    ohne Rolle und mit `aktiv=False` entsteht ("wartet auf Freischaltung",
    siehe app/routers/oidc.py) - eine Einrichtungs-Admin muss die Rolle
    bewusst zuweisen, statt dass sie implizit aus dem Identity-Provider
    übernommen wird (CLAUDE.md §8: "Rollen ... niemals implizit"). Die
    Invariante "aktiv=True ⇒ role ist gesetzt" wird ausschließlich beim
    Freischalten in app/routers/admin.py erzwungen.
    """

    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    password_hash: str | None = None
    role: RoleEnum | None = None
    auth_source: AuthSource = AuthSource.local
    # OIDC "sub" des Identity-Providers (z.B. Authentik) - stabile,
    # eindeutige Kennung der Person, unabhängig von E-Mail-Änderungen.
    external_id: str | None = Field(default=None, unique=True, index=True)
    abteilung_id: int | None = Field(default=None, foreign_key="abteilung.id")
    # Kontakt-Telefonnummer, hauptsächlich für Berufstrainer:innen/PSM/Admin
    # relevant (siehe app/routers/admin.py) - Teilnehmer:innen werden über
    # ihre zuständigen Kontaktpersonen erreicht, nicht umgekehrt.
    telefon: str | None = None
    # Deaktivierte Accounts können sich nicht mehr einloggen, bleiben aber
    # mit allen Daten erhalten und sind reaktivierbar - Zwischenstufe
    # zwischen "aktiv" und Löschung (siehe app/routers/admin.py).
    aktiv: bool = True
    letzter_login: datetime | None = None
    created_at: datetime = Field(default_factory=jetzt)
