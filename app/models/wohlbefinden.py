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

    # Wöchentlich rotierender Übungstyp (siehe app/core/tagesuebungen.py) -
    # bestimmt, welcher der Morgen-Bausteine unten tatsächlich angezeigt
    # wird; Name wird wie atemuebung_name mitgespeichert, damit er bei
    # erneutem Aufruf stabil bleibt, auch wenn der Pool später erweitert
    # wird. "atemuebung" nutzt weiterhin die Felder oben, alle anderen Typen
    # ihr jeweils eigenes schmales Ergebnis-Feld unten.
    morgen_uebung_typ: str | None = None
    koerperscan_erledigt_am: datetime | None = None
    grounding_erledigt_am: datetime | None = None
    wort_des_tages: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    staerken_karte_frage: str | None = None
    staerken_karte_antwort: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    staerken_karte_erledigt_am: datetime | None = None

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

    # Wöchentlich rotierender Übungstyp für den Abend-Teil, analog
    # morgen_uebung_typ oben. "zeichnung" nutzt weiterhin zeichnung_pfad,
    # alle anderen Typen ihr jeweils eigenes Feld unten.
    abend_uebung_typ: str | None = None
    mandala_erledigt_am: datetime | None = None
    ruhe_ort_sehen: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    ruhe_ort_hoeren: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    ruhe_ort_spueren: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    gedanke_belastend: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    gedanke_ausgewogen: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    # Bewusst NICHT gespeichert (nur der Abschluss-Zeitpunkt) - das
    # Loslassen selbst ist der Zweck der Übung, siehe VB-006.md.
    sorgen_los_erledigt_am: datetime | None = None
    # Wie zeichnung_pfad verschlüsselt auf der Platte abgelegt (siehe
    # app/core/uploads.py), hier nur der relative Pfad.
    dankbarkeitsfoto_pfad: str | None = None
    mini_ziel_text: str | None = Field(default=None, sa_column=Column(VerschluesselterText))
    mini_ziel_geschafft: bool = False

    check_pause_gemacht: bool = False
    check_jemandem_geholfen: bool = False
    check_kleines_erfolgserlebnis: bool = False
    abend_ausgefuellt_am: datetime | None = None

    erstellt_am: datetime = Field(default_factory=datetime.utcnow)


class WohlbefindenFreigabeUmfang(str, Enum):
    alle = "alle"
    zeitraum = "zeitraum"
    einzeln = "einzeln"


class WohlbefindenFreigabe(SQLModel, table=True):
    """Von der/dem Teilnehmer:in selbst erteilte, jederzeit widerrufbare
    Freigabe des eigenen Tagebuchs für eine bestimmte psychosoziale
    Mitarbeit (siehe app/routers/wohlbefinden.py,
    app/core/access.py:hat_wohlbefinden_freigabe).

    Ersetzt NICHT die organisatorische PsmZuordnung - beide müssen aktiv
    sein, damit die PSM tatsächlich lesen darf (Zuordnung = "wer ist
    zuständig", Freigabe = "darf auch wirklich sehen").

    Bei umfang=einzeln ist `tagebuch_eintrag_id` gesetzt und beschränkt die
    Freigabe auf genau diesen einen Tag - analog zu
    BewerbungsFreigabe.bewerbung_id bei umfang=einzeln dort. `gueltig_bis`
    bleibt bei einzeln ungenutzt (None): ein bereits geschriebener Tag
    bekommt kein Ablaufdatum, nur einen expliziten Widerruf.
    """

    id: int | None = Field(default=None, primary_key=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)
    empfaenger_id: int = Field(foreign_key="user.id", index=True)
    umfang: WohlbefindenFreigabeUmfang = WohlbefindenFreigabeUmfang.alle
    tagebuch_eintrag_id: int | None = Field(default=None, foreign_key="tagebucheintrag.id", index=True)
    gueltig_bis: date | None = None
    widerrufen_am: datetime | None = None
    erstellt_am: datetime = Field(default_factory=datetime.utcnow)


class Unterstuetzungsanfrage(SQLModel, table=True):
    """Bewusst eigenständige, freiwillige Aktion einer/eines Teilnehmer:in
    ("Ich möchte jetzt Unterstützung" in app/templates/wohlbefinden/
    uebersicht.html) - komplett unabhängig von Tagebuch-Inhalten und ohne
    jeden Freitext, nur Zeitpunkt + wer + an wen. Erscheint auf dem
    Dashboard der/des Empfänger:in (siehe app/main.py), bis sie/er die
    Anfrage als gesehen markiert (app/routers/wohlbefinden.py). Kein
    Status "erledigt" - das würde eine Bewertung der psychosozialen
    Situation durch die Empfänger:in nahelegen, die hier nicht Aufgabe der
    App ist."""

    id: int | None = Field(default=None, primary_key=True)
    teilnehmer_id: int = Field(foreign_key="user.id", index=True)
    empfaenger_id: int = Field(foreign_key="user.id", index=True)
    erstellt_am: datetime = Field(default_factory=datetime.utcnow)
    gesehen_am: datetime | None = None
