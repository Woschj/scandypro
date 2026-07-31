from datetime import date, datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class BoardTyp(str, Enum):
    team = "team"
    person = "person"


class Board(SQLModel, table=True):
    """Ein Board entspricht einem Projekt innerhalb eines Handlungsfelds
    (typ=team) oder der persönlichen Aufgabenliste einer/eines Teilnehmer:in
    (typ=person, siehe person_teilnehmer_id).

    Team-Boards werden von der Leitung des Handlungsfelds angelegt
    (ersteller_id) und für Teilnehmergruppen freigegeben (siehe
    BoardFreigabe). Personen-Boards werden lazy angelegt (erster Zugriff,
    siehe app/routers/kanban.py) und gehören genau einer/einem Teilnehmer:in.
    """

    id: int | None = Field(default=None, primary_key=True)
    titel: str
    typ: BoardTyp = BoardTyp.team
    handlungsfeld_id: int | None = Field(default=None, foreign_key="handlungsfeld.id", index=True)
    person_teilnehmer_id: int | None = Field(default=None, foreign_key="user.id", index=True)
    ersteller_id: int = Field(foreign_key="user.id")
    erstellt_am: datetime = Field(default_factory=datetime.utcnow)


class BoardFreigabe(SQLModel, table=True):
    """Gibt ein Team-Board für alle Mitglieder einer Teilnehmergruppe frei."""

    id: int | None = Field(default=None, primary_key=True)
    board_id: int = Field(foreign_key="board.id", index=True)
    gruppe_id: int = Field(foreign_key="teilnehmergruppe.id", index=True)
    freigegeben_am: datetime = Field(default_factory=datetime.utcnow)


class Spalte(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    board_id: int = Field(foreign_key="board.id")
    name: str
    reihenfolge: int = 0


class KartenSichtbarkeit(str, Enum):
    team = "team"
    privat = "privat"


class Karte(SQLModel, table=True):
    """Eine Kanban-Karte (Task).

    Auf Team-Boards immer sichtbarkeit=team (für alle mit Boardzugriff
    sichtbar). Auf Personen-Boards defaulten von der/dem Teilnehmer:in selbst
    erstellte Karten auf privat (nur für sie/ihn sichtbar); von einem
    zuständigen Trainer erstellte Karten sind für diesen Trainer automatisch
    sichtbar (er hat sie angelegt). Nur die/der Board-Owner darf die
    Sichtbarkeit einer eigenen Karte ändern (siehe app/core/access.py,
    sichtbare_karten_filter).
    """

    id: int | None = Field(default=None, primary_key=True)
    spalte_id: int = Field(foreign_key="spalte.id")
    titel: str
    beschreibung: str | None = None
    faelligkeit: date | None = None
    ersteller_id: int = Field(foreign_key="user.id")
    sichtbarkeit: KartenSichtbarkeit = KartenSichtbarkeit.team
    reihenfolge: int = 0
    erstellt_am: datetime = Field(default_factory=datetime.utcnow)


class KartenZuweisung(SQLModel, table=True):
    """Zuweisung einer Karte an eine Person (m:n - eine Karte kann mehrere
    Zuständige haben)."""

    id: int | None = Field(default=None, primary_key=True)
    karte_id: int = Field(foreign_key="karte.id", index=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)


class Unteraufgabe(SQLModel, table=True):
    """Checklisten-Eintrag innerhalb einer Karte (eine Ebene, keine eigene
    Karte/Spalte - siehe KONZEPT.md)."""

    id: int | None = Field(default=None, primary_key=True)
    karte_id: int = Field(foreign_key="karte.id", index=True)
    titel: str
    erledigt: bool = False
    zugewiesen_an: int | None = Field(default=None, foreign_key="user.id")
    reihenfolge: int = 0
    erstellt_am: datetime = Field(default_factory=datetime.utcnow)
