from datetime import date, datetime
from enum import Enum

from sqlalchemy import Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.crypto import VerschluesselterText


class WohlbefindenEintrag(SQLModel, table=True):
    """Hochsensibel (Art. 9 DSGVO).

    Ein Eintrag pro Tag mit zwei Werten (1-10, per Emoji-Kachel antippbar -
    siehe app/core/skala.py für die Emoji-Zuordnung):
    - stimmung: die "Wohlbefinden"-Linie
    - belastbarkeit: wie viel Kapazität an diesem Tag gefühlt vorhanden war

    `kommentar` liegt feldverschlüsselt in der DB (siehe app/core/crypto.py) -
    Zugriff für Dritte nur über aktive WohlbefindenFreigabe (siehe
    app/models/wohlbefinden.py weiter unten, app/core/access.py).
    """

    __table_args__ = (UniqueConstraint("teilnehmer_id", "datum"),)

    id: int | None = Field(default=None, primary_key=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)
    datum: date = Field(index=True)
    stimmung: int = Field(ge=1, le=10)
    belastbarkeit: int = Field(ge=1, le=10)
    kommentar: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    erstellt_am: datetime = Field(default_factory=datetime.utcnow)
    aktualisiert_am: datetime = Field(default_factory=datetime.utcnow)


class WohlbefindenFreigabeUmfang(str, Enum):
    alle = "alle"
    zeitraum = "zeitraum"


class WohlbefindenFreigabe(SQLModel, table=True):
    """Von der/dem Teilnehmer:in selbst erteilte, jederzeit widerrufbare
    Freigabe der eigenen Wohlbefinden-Daten für eine bestimmte
    psychosoziale Mitarbeit (siehe app/routers/wohlbefinden.py,
    app/core/access.py:hat_wohlbefinden_freigabe).

    Ersetzt NICHT die organisatorische PsmZuordnung - beide müssen aktiv
    sein, damit die PSM tatsächlich lesen darf (Zuordnung = "wer ist
    zuständig", Freigabe = "darf auch wirklich sehen").
    """

    id: int | None = Field(default=None, primary_key=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)
    empfaenger_id: int = Field(foreign_key="user.id", index=True)
    umfang: WohlbefindenFreigabeUmfang = WohlbefindenFreigabeUmfang.alle
    gueltig_bis: date | None = None
    widerrufen_am: datetime | None = None
    erstellt_am: datetime = Field(default_factory=datetime.utcnow)
