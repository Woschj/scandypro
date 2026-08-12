"""Tests der Schlüsselrotation (PR-004, app/core/crypto.py).

Die Rotation ist der Vorgang mit dem höchsten Schadenspotenzial im ganzen
Projekt: Wer den alten Schlüssel entfernt, bevor die Bestandsdaten
umgeschrieben sind, macht Tagebücher und Bewerbungsunterlagen **dauerhaft**
unlesbar - auch aus dem Backup heraus, weil dort derselbe Ciphertext liegt.

Entsprechend liegt der Schwerpunkt nicht auf "funktioniert das Umschreiben",
sondern auf den Eigenschaften, die verhindern, dass jemand sich selbst
aussperrt:

- Mit mehreren Schlüsseln bleiben Altdaten lesbar (sonst wäre Schritt 1 der
  Rotation schon der Datenverlust).
- Neue Daten nutzen wirklich den neuen Schlüssel, nicht irgendeinen aus der
  Liste.
- Der Prüfmodus erkennt zuverlässig, ob noch etwas am alten Schlüssel hängt.
"""
import importlib

import pytest
from cryptography.fernet import Fernet, InvalidToken

ALT = Fernet.generate_key().decode()
NEU = Fernet.generate_key().decode()
FREMD = Fernet.generate_key().decode()


def _crypto_mit(schluessel: str):
    """Lädt app.core.crypto mit einer bestimmten Schlüsselliste neu.

    Nötig, weil das Modul die Fernet-Instanzen beim Import baut - genau wie
    im Produktivbetrieb, wo ein Schlüsselwechsel einen Neustart erfordert.
    """
    from app.core.config import settings

    settings.field_encryption_key = schluessel
    import app.core.crypto as crypto_modul

    return importlib.reload(crypto_modul)


@pytest.fixture(autouse=True)
def crypto_zuruecksetzen():
    """Nach jedem Test den Originalzustand wiederherstellen - sonst laufen
    andere Testmodule gegen einen fremden Schlüssel."""
    from app.core.config import settings

    original = settings.field_encryption_key
    yield
    settings.field_encryption_key = original
    import app.core.crypto as crypto_modul

    importlib.reload(crypto_modul)


# ---------------------------------------------------------------------------
# Rückwärtskompatibilität
# ---------------------------------------------------------------------------


def test_einzelner_schluessel_verhaelt_sich_unveraendert():
    """Bestehende Installationen haben genau einen Schlüssel und dürfen von
    der Rotationsfähigkeit nichts merken."""
    crypto = _crypto_mit(ALT)
    assert crypto.anzahl_schluessel() == 1
    token = crypto.verschluesseln("Ein gutes Gespräch mit einer Kollegin.")
    assert crypto.entschluesseln(token) == "Ein gutes Gespräch mit einer Kollegin."


def test_leerzeichen_in_der_schluesselliste_stoeren_nicht():
    crypto = _crypto_mit(f" {NEU} , {ALT} ")
    assert crypto.anzahl_schluessel() == 2


def test_leerer_schluessel_faellt_sofort_auf():
    from app.core.config import settings

    settings.field_encryption_key = "  "
    import app.core.crypto as crypto_modul

    with pytest.raises(ValueError):
        importlib.reload(crypto_modul)


# ---------------------------------------------------------------------------
# Schritt 1 der Rotation: neuer Schlüssel vorne, Altdaten bleiben lesbar
# ---------------------------------------------------------------------------


def test_altdaten_bleiben_nach_dem_anhaengen_lesbar():
    """Der Moment, in dem ein Fehler alles kosten würde."""
    alt_crypto = _crypto_mit(ALT)
    altes_token = alt_crypto.verschluesseln("Bewerbung bei Musterfirma abgeschickt")

    rotiert = _crypto_mit(f"{NEU},{ALT}")
    assert rotiert.entschluesseln(altes_token) == "Bewerbung bei Musterfirma abgeschickt"


def test_neue_daten_nutzen_den_neuen_schluessel():
    rotiert = _crypto_mit(f"{NEU},{ALT}")
    token = rotiert.verschluesseln("frisch geschrieben")

    # Mit dem neuen Schlüssel allein lesbar …
    nur_neu = _crypto_mit(NEU)
    assert nur_neu.entschluesseln(token) == "frisch geschrieben"

    # … mit dem alten allein nicht.
    nur_alt = _crypto_mit(ALT)
    with pytest.raises(InvalidToken):
        nur_alt.entschluesseln(token)


def test_unbekannter_schluessel_wird_nicht_akzeptiert():
    fremd_crypto = _crypto_mit(FREMD)
    fremdes_token = fremd_crypto.verschluesseln("gehoert nicht hierher")

    rotiert = _crypto_mit(f"{NEU},{ALT}")
    with pytest.raises(InvalidToken):
        rotiert.entschluesseln(fremdes_token)


# ---------------------------------------------------------------------------
# Prüfmodus: hängt noch etwas am alten Schlüssel?
# ---------------------------------------------------------------------------


def test_pruefung_erkennt_altdaten():
    alt_crypto = _crypto_mit(ALT)
    altes_token = alt_crypto.verschluesseln("noch auf dem alten Schluessel")

    rotiert = _crypto_mit(f"{NEU},{ALT}")
    assert rotiert.ist_aktuell_verschluesselt(altes_token) is False

    neues_token = rotiert.verschluesseln("schon neu")
    assert rotiert.ist_aktuell_verschluesselt(neues_token) is True


def test_pruefung_arbeitet_auch_auf_bytes():
    """Dateien werden als bytes geprüft, DB-Felder als str."""
    alt_crypto = _crypto_mit(ALT)
    altes_token = alt_crypto.verschluessle_bytes(b"%PDF-1.7 Lebenslauf")

    rotiert = _crypto_mit(f"{NEU},{ALT}")
    assert rotiert.ist_aktuell_verschluesselt(altes_token) is False
    assert rotiert.ist_aktuell_verschluesselt(rotiert.verschluessle_bytes(b"neu")) is True


# ---------------------------------------------------------------------------
# Schritt 2: Umschreiben
# ---------------------------------------------------------------------------


def test_umschreiben_macht_daten_ohne_alten_schluessel_lesbar():
    """Der eigentliche Zweck: nach dem Umschreiben darf der alte Schlüssel
    weg, ohne dass Daten verloren gehen."""
    alt_crypto = _crypto_mit(ALT)
    altes_token = alt_crypto.verschluesseln("Zeit für eine kurze Pause gehabt.")

    rotiert = _crypto_mit(f"{NEU},{ALT}")
    neues_token = rotiert.neu_verschluesseln(altes_token).decode()
    assert rotiert.ist_aktuell_verschluesselt(neues_token) is True

    # Alter Schlüssel entfernt - Inhalt trotzdem da.
    nur_neu = _crypto_mit(NEU)
    assert nur_neu.entschluesseln(neues_token) == "Zeit für eine kurze Pause gehabt."


def test_umschreiben_erhaelt_dateiinhalte_bytegenau():
    inhalt = bytes(range(256)) * 40
    alt_crypto = _crypto_mit(ALT)
    altes_token = alt_crypto.verschluessle_bytes(inhalt)

    rotiert = _crypto_mit(f"{NEU},{ALT}")
    neues_token = rotiert.neu_verschluesseln(altes_token)

    nur_neu = _crypto_mit(NEU)
    assert nur_neu.entschluessle_bytes(neues_token) == inhalt


def test_umschreiben_ist_wiederholbar():
    """Das Skript kann nach einem Abbruch erneut laufen - ein bereits
    umgeschriebener Wert darf dabei nicht kaputtgehen."""
    rotiert = _crypto_mit(f"{NEU},{ALT}")
    token = rotiert.verschluesseln("schon aktuell")
    nochmal = rotiert.neu_verschluesseln(rotiert.neu_verschluesseln(token))
    assert rotiert.entschluesseln(nochmal.decode()) == "schon aktuell"


# ---------------------------------------------------------------------------
# Der Fehler, der alles kostet
# ---------------------------------------------------------------------------


def test_alten_schluessel_zu_frueh_entfernen_macht_daten_unlesbar():
    """Dokumentiert bewusst den Schadensfall, gegen den der Prüfmodus
    schützt: ohne vorheriges Umschreiben ist nach dem Entfernen Schluss -
    und zwar endgültig, auch aus dem Backup heraus, weil dort derselbe
    Ciphertext liegt."""
    alt_crypto = _crypto_mit(ALT)
    altes_token = alt_crypto.verschluesseln("Diagnose im Freitext")

    # Schritt 3 ohne Schritt 2:
    nur_neu = _crypto_mit(NEU)
    with pytest.raises(InvalidToken):
        nur_neu.entschluesseln(altes_token)

    # Und der Prüfmodus hätte genau davor gewarnt.
    rotiert = _crypto_mit(f"{NEU},{ALT}")
    assert rotiert.ist_aktuell_verschluesselt(altes_token) is False
