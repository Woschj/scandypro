from datetime import date, datetime
from enum import Enum

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from app.core.crypto import VerschluesselterText


class BewerbungStatus(str, Enum):
    entwurf = "entwurf"
    versendet = "versendet"
    rueckmeldung_offen = "rueckmeldung_offen"
    eingeladen = "eingeladen"
    abgesagt = "abgesagt"
    zugesagt = "zugesagt"


class Bewerbung(SQLModel, table=True):
    """Sensibel (potenziell diskriminierungsrelevant), gedacht als per Status
    verschiebbares "Workitem" analog zu einer Kanban-Karte (siehe
    app/templates/bewerbungen/uebersicht.html: Board-Ansicht,
    app/models/kanban.py:Karte fürs Vorbild) - `status` entspricht dabei der
    Spalte. Freitext-Verlauf liegt nicht mehr in einem einzelnen Feld,
    sondern in BewerbungsNotiz (siehe unten, mehrere pro Bewerbung)."""

    id: int | None = Field(default=None, primary_key=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)
    firma: str
    position: str
    status: BewerbungStatus = BewerbungStatus.entwurf
    beworben_am: date | None = None
    naechster_termin: date | None = None
    # Uhrzeit als "HH:MM"-Text statt vollem datetime-Feld, um die
    # bestehende reine Datums-Arithmetik auf naechster_termin (siehe
    # app/routers/bewerbungen.py:_ausstehende_rueckmeldungen) nicht
    # anzufassen - für ein Vorstellungsgespräch reicht das für Anzeige-
    # zwecke, ohne Zeitzonen-/Kombinationslogik einzuführen.
    naechster_termin_uhrzeit: str | None = None
    naechster_termin_ort: str | None = None
    erstellt_am: datetime = Field(default_factory=datetime.utcnow)


class BewerbungsNotiz(SQLModel, table=True):
    """Eine einzelne, feldverschlüsselte Notiz zu einer Bewerbung (z.B.
    "Telefonat geführt", "Zusage laut Anruf") - ersetzt das frühere
    einzelne Bewerbung.notizen-Feld durch einen wachsenden Verlauf,
    analog zu Unteraufgabe bei einer Kanban-Karte. Reine Anhäng-/Lösch-
    Historie, kein Bearbeiten bestehender Einträge (Verlauf soll
    nachvollziehbar bleiben)."""

    id: int | None = Field(default=None, primary_key=True)
    bewerbung_id: int = Field(foreign_key="bewerbung.id", index=True)
    text: str = Field(sa_column=Column(VerschluesselterText))
    erstellt_am: datetime = Field(default_factory=datetime.utcnow)


class UnterlagenKategorie(str, Enum):
    lebenslauf = "lebenslauf"
    zeugnis = "zeugnis"
    anschreiben = "anschreiben"
    deckblatt = "deckblatt"


class Bewerbungsunterlage(SQLModel, table=True):
    """Hochgeladene Datei zu Bewerbungen.

    Lebenslauf/Zeugnisse gehören der/dem Teilnehmer:in direkt (einmal
    hochgeladen, für alle eigenen Bewerbungen wiederverwendbar) - `reihenfolge`
    bestimmt hier die Reihenfolge im PDF-Export (siehe
    app/routers/bewerbungen.py, per Auf/Ab-Buttons änderbar).
    Anschreiben und Deckblatt gehören zu genau einer Bewerbung
    (bewerbung_id gesetzt) - das Deckblatt erscheint im PDF-Export vor dem
    Anschreiben, beide vor den Lebenslauf-/Zeugnis-Unterlagen.

    `speicherpfad` ist relativ zu settings.upload_dir und enthält einen
    zufälligen Dateinamen (siehe app/core/uploads.py) - `original_dateiname`
    ist nur ein Anzeige-Metadatum, nie Teil des Dateisystem-Pfads.
    """

    id: int | None = Field(default=None, primary_key=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)
    kategorie: UnterlagenKategorie
    bewerbung_id: int | None = Field(default=None, foreign_key="bewerbung.id", index=True)
    original_dateiname: str
    speicherpfad: str
    groesse_bytes: int
    reihenfolge: int = 0
    hochgeladen_am: datetime = Field(default_factory=datetime.utcnow)


class BewerbungsFreigabeUmfang(str, Enum):
    alle = "alle"
    einzeln = "einzeln"


class BewerbungsFreigabe(SQLModel, table=True):
    """Von der/dem Teilnehmer:in selbst erteilte, jederzeit widerrufbare
    Freigabe der eigenen Bewerbungsdaten für einen bestimmten Berufstrainer
    (siehe app/routers/bewerbungen.py, app/core/access.py:
    hat_bewerbungs_freigabe).

    Ersetzt NICHT die organisatorische BerufstrainerZuordnung - beide
    müssen aktiv sein, damit der Trainer tatsächlich lesen darf.
    """

    id: int | None = Field(default=None, primary_key=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)
    empfaenger_id: int = Field(foreign_key="user.id", index=True)
    umfang: BewerbungsFreigabeUmfang = BewerbungsFreigabeUmfang.alle
    bewerbung_id: int | None = Field(default=None, foreign_key="bewerbung.id", index=True)
    gueltig_bis: date | None = None
    widerrufen_am: datetime | None = None
    erstellt_am: datetime = Field(default_factory=datetime.utcnow)
