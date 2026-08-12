from datetime import date, datetime
from enum import Enum

from sqlmodel import Field, SQLModel
from app.core.zeit import jetzt


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
    # Nullbar, damit ein Konto vollständig gelöscht werden kann (Art. 17
    # DSGVO, siehe app/core/deletion.py:loesche_konto_vollstaendig). Der
    # Inhalt bleibt bestehen und wird als "Gelöschte:r Nutzer:in" angezeigt -
    # auf Team-Boards arbeiten andere Menschen weiter, deren Karten nicht
    # verschwinden dürfen, nur weil eine Person das Haus verlässt.
    ersteller_id: int | None = Field(default=None, foreign_key="user.id")
    erstellt_am: datetime = Field(default_factory=jetzt)


class BoardFreigabe(SQLModel, table=True):
    """Gibt ein Team-Board für einen Personenkreis frei - genau eines von
    `gruppe_id` (eine Arbeitsgruppe), `handlungsfeld_id` (alle Mitglieder
    des ganzen Handlungsfelds) oder `teilnehmer_id` (eine einzelne Person)
    ist gesetzt, die anderen beiden bleiben None. Die Anwendungslogik
    (app/routers/kanban.py:freigabe_erstellen) stellt das sicher - kein
    DB-Constraint dafür, analog zu anderen optionalen Freigabe-Feldern im
    Projekt (z.B. BewerbungsFreigabe.bewerbung_id)."""

    id: int | None = Field(default=None, primary_key=True)
    board_id: int = Field(foreign_key="board.id", index=True)
    gruppe_id: int | None = Field(default=None, foreign_key="teilnehmergruppe.id", index=True)
    handlungsfeld_id: int | None = Field(default=None, foreign_key="handlungsfeld.id", index=True)
    teilnehmer_id: int | None = Field(default=None, foreign_key="user.id", index=True)
    freigegeben_am: datetime = Field(default_factory=jetzt)


class Spalte(SQLModel, table=True):
    """Eine Spalte auf genau einem Board.

    ist_system_erledigt markiert die eine, fest verankerte "Erledigt"-Spalte
    jedes Boards (siehe app/routers/kanban.py:STANDARD_SPALTEN) - immer die
    letzte Spalte, kann nicht gelöscht werden, Karten darin gelten als
    abgeschlossen und sind nicht mehr editierbar (siehe
    app/routers/kanban_karten.py:_karte_ist_gesperrt). Macht das positive
    Feedback beim Verschieben zuverlässig, unabhängig davon, wie Trainer:innen
    ihre übrigen Spalten benennen/anordnen."""

    id: int | None = Field(default=None, primary_key=True)
    board_id: int = Field(foreign_key="board.id")
    name: str
    reihenfolge: int = 0
    ist_system_erledigt: bool = False


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
    # Nullbar, damit ein Konto vollständig gelöscht werden kann (Art. 17
    # DSGVO, siehe app/core/deletion.py:loesche_konto_vollstaendig). Der
    # Inhalt bleibt bestehen und wird als "Gelöschte:r Nutzer:in" angezeigt -
    # auf Team-Boards arbeiten andere Menschen weiter, deren Karten nicht
    # verschwinden dürfen, nur weil eine Person das Haus verlässt.
    ersteller_id: int | None = Field(default=None, foreign_key="user.id")
    sichtbarkeit: KartenSichtbarkeit = KartenSichtbarkeit.team
    reihenfolge: int = 0
    erstellt_am: datetime = Field(default_factory=jetzt)
    abgeschlossen_am: datetime | None = None
    """Gesetzt, sobald die Karte in die fest verankerte Erledigt-Spalte
    verschoben wird (siehe Spalte.ist_system_erledigt); wieder None, wenn
    sie herausgezogen wird. Grundlage für das private Wochen-Fortschritts-
    Signal (siehe app/core/fortschritt.py) - bewusst kein allgemeines
    Aktivitäts-/Audit-Log, nur dieses eine schmale Feld."""


class KartenBewegung(SQLModel, table=True):
    """Protokolliert jede Vorwärtsbewegung einer Karte (Ziel-Spalte hat eine
    höhere `reihenfolge` als die Ausgangs-Spalte) - Grundlage für das
    private Wochen-Fortschritts-Signal (siehe app/core/fortschritt.py:
    woechentliche_schritte). Bewusst nur Vorwärtsbewegungen: Zurückziehen
    einer Karte wird nicht protokolliert, zählt aber auch nirgends negativ
    (siehe CLAUDE.md "keine Leistungsbegriffe"). Kein allgemeines
    Aktivitäts-/Audit-Log - nur dieses eine schmale, zweckgebundene Signal,
    wer eine Karte wann einen Schritt weitergebracht hat."""

    id: int | None = Field(default=None, primary_key=True)
    karte_id: int = Field(foreign_key="karte.id", index=True)
    # Nullbar, damit ein Konto vollständig gelöscht werden kann (Art. 17
    # DSGVO, siehe app/core/deletion.py:loesche_konto_vollstaendig). Der
    # Inhalt bleibt bestehen und wird als "Gelöschte:r Nutzer:in" angezeigt -
    # auf Team-Boards arbeiten andere Menschen weiter, deren Karten nicht
    # verschwinden dürfen, nur weil eine Person das Haus verlässt.
    bewegt_von_id: int | None = Field(default=None, foreign_key="user.id", index=True)
    bewegt_am: datetime = Field(default_factory=jetzt)


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
    erstellt_am: datetime = Field(default_factory=jetzt)
    erledigt_am: datetime | None = None
