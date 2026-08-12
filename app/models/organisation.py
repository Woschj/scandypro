from datetime import datetime

from sqlmodel import Field, SQLModel
from app.core.zeit import jetzt


class Abteilung(SQLModel, table=True):
    """Feste Struktureinheit der Einrichtung (z.B. Medien & Digital).

    Name ist über die Admin-Verwaltung änderbar (siehe app/routers/admin.py).
    """

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)


class Handlungsfeld(SQLModel, table=True):
    """Konkretes Arbeitsgebiet innerhalb einer Abteilung (z.B. "Video-
    Projekte" in Medien & Digital) - die eigentliche operative Einheit, in
    der Teilnehmer:innen zusammenarbeiten. Angelehnt an das gleichnamige
    Konzept in Scandy2 (dort: abteilungsgebundene Ticket-Kategorie).

    Boards und Teilnehmergruppen hängen an einem Handlungsfeld, nicht mehr
    direkt an der Abteilung - die Abteilung ist nur noch die grobe Klammer.
    """

    id: int | None = Field(default=None, primary_key=True)
    name: str
    abteilung_id: int = Field(foreign_key="abteilung.id", index=True)


class HandlungsfeldLeitung(SQLModel, table=True):
    """Ein Berufstrainer leitet ein Handlungsfeld (m:n - ein Handlungsfeld
    kann mehrere Leitungen haben, ein Trainer mehrere Handlungsfelder).

    Nur Leitungen eines Handlungsfelds dürfen dessen Boards/Gruppen
    verwalten (siehe app/core/access.py) - das ersetzt die bisherige
    Prototyp-Vereinfachung "jeder Berufstrainer darf alles".
    """

    id: int | None = Field(default=None, primary_key=True)
    handlungsfeld_id: int = Field(foreign_key="handlungsfeld.id", index=True)
    berufstrainer_id: int = Field(foreign_key="user.id", index=True)


class Teilnehmergruppe(SQLModel, table=True):
    """Von einer Handlungsfeld-Leitung angelegte Gruppe aus Teilnehmenden.

    Boards werden nicht an einzelne Teilnehmer, sondern an solche Gruppen
    freigegeben (siehe BoardFreigabe) - so arbeiten mehrere Teilnehmende
    gemeinsam an einem Board/Projekt eines Handlungsfelds.
    """

    id: int | None = Field(default=None, primary_key=True)
    name: str
    handlungsfeld_id: int = Field(foreign_key="handlungsfeld.id", index=True)
    erstellt_von: int = Field(foreign_key="user.id")
    erstellt_am: datetime = Field(default_factory=jetzt)


class TeilnehmergruppeMitglied(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    gruppe_id: int = Field(foreign_key="teilnehmergruppe.id", index=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)


class HandlungsfeldMitglied(SQLModel, table=True):
    """Direkte Mitgliedschaft einer/eines Teilnehmer:in in einem Handlungsfeld.

    Quelle der Wahrheit dafür, wer zu einem Handlungsfeld gehört - unabhängig
    davon, ob die Person zusätzlich einer projektbezogenen Teilnehmergruppe
    angehört. Verwaltet von der Leitung des Handlungsfelds (siehe
    app/routers/kanban.py).
    """

    id: int | None = Field(default=None, primary_key=True)
    handlungsfeld_id: int = Field(foreign_key="handlungsfeld.id", index=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)
    hinzugefuegt_am: datetime = Field(default_factory=jetzt)


class PsmZuordnung(SQLModel, table=True):
    """Organisatorische Zuordnung: welche psychosoziale Mitarbeit betreut
    welche:n Teilnehmer:in.

    Gewährt bewusst KEINEN automatischen Zugriff auf Wohlbefinden-Daten -
    das bleibt ausschließlich über die Freigabe/Consent-Funktion des
    Teilnehmers geregelt (siehe docs/DATENSCHUTZ_UND_BERECHTIGUNGEN.md).
    Dient nur der Anzeige "das ist deine PSM-Kontaktperson".
    """

    id: int | None = Field(default=None, primary_key=True)
    psm_id: int = Field(foreign_key="user.id", index=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)
    erstellt_am: datetime = Field(default_factory=jetzt)


class BerufstrainerZuordnung(SQLModel, table=True):
    """Organisatorische Zuordnung: welcher Berufstrainer betreut welche:n
    Teilnehmer:in persönlich - analog PsmZuordnung.

    Gewährt KEINEN automatischen Zugriff auf Wohlbefinden/Bewerbungen (das
    bleibt Consent-basiert). Dient aber als zweite Zugriffsgrundlage (neben
    Handlungsfeld-Leitung) dafür, dass ein Trainer persönliche Kanban-Items
    für diese:n Teilnehmer:in anlegen/sehen darf (siehe app/core/access.py,
    ist_zustaendiger_trainer).
    """

    id: int | None = Field(default=None, primary_key=True)
    berufstrainer_id: int = Field(foreign_key="user.id", index=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)
    erstellt_am: datetime = Field(default_factory=jetzt)
