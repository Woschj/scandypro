from datetime import date, datetime
from enum import Enum

from sqlalchemy import Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.crypto import VerschluesselterText


class TagebuchEintrag(SQLModel, table=True):
    """5-Minuten-Tagebuch ("Mein Tag") - hochsensibel (Art. 9 DSGVO).

    Ersetzt die frühere Stimmungs-/Energie-Skala (1-10) vollständig: statt
    einer Zahl, die als Trend "besser/schlechter" gelesen werden könnte,
    schreibt die Person freie Sätze - näher an Journaling-Praxis, ohne
    implizite Bewertung. Ein Eintrag pro Tag, Morgen- und Abend-Teil
    unabhängig voneinander speicherbar (morgen_ausgefuellt_am/
    abend_ausgefuellt_am zeigen an, was schon erledigt ist).

    Jede Tageszeit hat einen festen Kernimpuls (morgens: Dankbarkeit,
    abends: großartige Dinge) plus einen täglich rotierenden zweiten
    Impuls (siehe app/core/tagebuch_prompts.py) - die tatsächlich gestellte
    Frage wird mitgespeichert (*_impuls_frage), damit sie auch bei
    späterer Ansicht/Freigabe stabil bleibt.

    Alle Freitextantworten liegen feldverschlüsselt in der DB (siehe
    app/core/crypto.py) - Zugriff für Dritte nur über aktive
    WohlbefindenFreigabe (siehe unten, app/core/access.py). Hard-Delete
    beim Löschen (siehe app/routers/freigaben.py).
    """

    __table_args__ = (UniqueConstraint("teilnehmer_id", "datum"),)

    id: int | None = Field(default=None, primary_key=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)
    datum: date = Field(index=True)

    dankbarkeit_1: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    dankbarkeit_2: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    dankbarkeit_3: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    morgen_impuls_frage: str | None = None
    morgen_impuls_antwort: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    # Batterie-Symbol statt Zahlenwert im UI (siehe uebersicht.html) - rein
    # privat, taucht bewusst NIE im Dashboard/Verlauf als Trend auf (siehe
    # CLAUDE.md "keine roten Warnsymbole"): anders als die frühere
    # Stimmungsskala dient dieser Wert nur der Person selbst im Moment,
    # nicht dem Vergleich über Tage hinweg.
    energie_level: int | None = None
    # Verbinde-die-Punkte-Atemübung vor dem Schreiben - täglich rotierend
    # aus einem Pool (siehe app/core/atemuebungen.py), der Name wird
    # mitgespeichert (analog *_impuls_frage) damit er bei erneutem Aufruf
    # stabil bleibt. Nur der Zeitpunkt des Abschlusses wird gespeichert
    # (kein Zeichenpfad), da der eigentliche Nutzen die kurze Pause selbst
    # ist, nicht ihr Ergebnis.
    atemuebung_name: str | None = None
    atemuebung_erledigt_am: datetime | None = None
    morgen_ausgefuellt_am: datetime | None = None

    highlight_1: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    highlight_2: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    highlight_3: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    abend_impuls_frage: str | None = None
    abend_impuls_antwort: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    # Freihand-Zeichnung ("Male, was dich heute gefreut hat") - wie
    # Bewerbungsunterlagen (app/core/uploads.py) verschlüsselt auf der
    # Platte abgelegt, hier nur der relative Pfad. Wird beim Ersetzen/
    # Löschen des Eintrags mitgelöscht (siehe app/routers/wohlbefinden.py,
    # app/core/deletion.py) - genauso hart löschbar wie der restliche
    # Tagebuch-Inhalt.
    zeichnung_pfad: str | None = None
    check_pause_gemacht: bool = False
    check_jemandem_geholfen: bool = False
    check_kleines_erfolgserlebnis: bool = False
    abend_ausgefuellt_am: datetime | None = None

    erstellt_am: datetime = Field(default_factory=datetime.utcnow)


class WohlbefindenFreigabeUmfang(str, Enum):
    alle = "alle"
    zeitraum = "zeitraum"


class WohlbefindenFreigabe(SQLModel, table=True):
    """Von der/dem Teilnehmer:in selbst erteilte, jederzeit widerrufbare
    Freigabe des eigenen Tagebuchs für eine bestimmte psychosoziale
    Mitarbeit (siehe app/routers/wohlbefinden.py,
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
