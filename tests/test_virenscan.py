"""Tests für die Virenprüfung von Uploads (PR-003, app/core/virenscan.py).

Getestet wird gegen einen nachgebauten clamd, der das INSTREAM-Protokoll
spricht - ein echter ClamAV-Container im Test würde ~1 GB Signaturen laden
und die Testlaufzeit unbrauchbar machen. Der Fake deckt genau das ab, was
in unserem Code entscheidet: die Antwortzeile.

Der Fall, der hier am meisten zählt, ist nicht der Virenfund, sondern der
**nicht erreichbare Scanner**. Ein Scanner, der still übersprungen wird,
ist gefährlicher als gar keiner, weil er Sicherheit vortäuscht.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.core import virenscan
from app.core.config import settings

# Offizielle EICAR-Testsignatur - kein echter Schadcode, sondern die von
# Antivirenherstellern vereinbarte Zeichenkette zum Testen von Scannern.
# Zusammengesetzt, damit die Datei nicht selbst bei jedem Scan des Repos
# anschlägt.
EICAR = (
    r"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-"
    + "ANTIVIRUS-TEST-FILE!$H+H*"
).encode()


class FakeClamd:
    """Minimaler clamd-Ersatz: liest einen INSTREAM-Strom und antwortet."""

    def __init__(self, antwort: bytes, verzoegerung: float = 0.0):
        self.antwort = antwort
        self.verzoegerung = verzoegerung
        self.empfangen = bytearray()
        self.server = None
        self.port = None

    async def __aenter__(self):
        self.server = await asyncio.start_server(self._behandle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *_):
        self.server.close()
        await self.server.wait_closed()

    async def _behandle(self, leser, schreiber):
        kommando = await leser.readuntil(b"\0")
        assert kommando == b"zINSTREAM\0", kommando
        while True:
            laenge_bytes = await leser.readexactly(4)
            laenge = int.from_bytes(laenge_bytes, "big")
            if laenge == 0:
                break
            self.empfangen.extend(await leser.readexactly(laenge))
        if self.verzoegerung:
            await asyncio.sleep(self.verzoegerung)
        schreiber.write(self.antwort)
        await schreiber.drain()
        schreiber.close()


@pytest.fixture
def scanner_konfiguriert(monkeypatch):
    """Setzt Host/Port auf den Fake und stellt danach wieder her."""

    def _konfiguriere(port: int, timeout: float = 5.0):
        monkeypatch.setattr(settings, "clamav_host", "127.0.0.1")
        monkeypatch.setattr(settings, "clamav_port", port)
        monkeypatch.setattr(settings, "clamav_timeout_sekunden", timeout)

    return _konfiguriere


# ---------------------------------------------------------------------------
# Abgeschaltet
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ohne_konfiguration_wird_nicht_geprueft(monkeypatch):
    """Prototyp-Standard: ohne CLAMAV_HOST läuft alles wie bisher durch."""
    monkeypatch.setattr(settings, "clamav_host", None)
    assert virenscan.virenscan_aktiv() is False
    await virenscan.pruefe_auf_schadsoftware(EICAR, "test.pdf")  # darf nicht werfen


# ---------------------------------------------------------------------------
# Normalbetrieb
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_saubere_datei_passiert(scanner_konfiguriert):
    async with FakeClamd(b"stream: OK\0") as clamd:
        scanner_konfiguriert(clamd.port)
        await virenscan.pruefe_auf_schadsoftware(b"%PDF-1.7 harmloser Inhalt", "lebenslauf.pdf")
    assert bytes(clamd.empfangen) == b"%PDF-1.7 harmloser Inhalt"


@pytest.mark.asyncio
async def test_fund_wird_abgelehnt(scanner_konfiguriert):
    async with FakeClamd(b"stream: Eicar-Signature FOUND\0") as clamd:
        scanner_konfiguriert(clamd.port)
        with pytest.raises(HTTPException) as fehler:
            await virenscan.pruefe_auf_schadsoftware(EICAR, "verdaechtig.pdf")
    assert fehler.value.status_code == 400
    # Sprache muss zum Reha-Kontext passen (CLAUDE.md §24): keine
    # Schuldzuweisung, ein klarer nächster Schritt.
    assert "Ansprechperson" in fehler.value.detail
    assert "muss nichts mit dir zu tun haben" in fehler.value.detail


@pytest.mark.asyncio
async def test_grosse_datei_wird_vollstaendig_uebertragen(scanner_konfiguriert):
    """INSTREAM zerlegt in Blöcke - dabei darf nichts verloren gehen, sonst
    würde der Scanner nur einen Teil der Datei sehen."""
    inhalt = bytes(range(256)) * 8000  # ~2 MB, mehrere Chunks
    async with FakeClamd(b"stream: OK\0") as clamd:
        scanner_konfiguriert(clamd.port)
        await virenscan.pruefe_auf_schadsoftware(inhalt, "gross.pdf")
    assert bytes(clamd.empfangen) == inhalt


# ---------------------------------------------------------------------------
# Fail closed - der eigentlich wichtige Teil
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nicht_erreichbarer_scanner_lehnt_ab(scanner_konfiguriert):
    """Konfigurierter, aber toter Scanner: Upload muss abgelehnt werden.
    Ein stilles Durchwinken wäre die gefährlichste Variante."""
    # Port, auf dem nichts lauscht.
    scanner_konfiguriert(1, timeout=2.0)
    with pytest.raises(HTTPException) as fehler:
        await virenscan.pruefe_auf_schadsoftware(b"irgendwas", "datei.pdf")
    assert fehler.value.status_code == 503


@pytest.mark.asyncio
async def test_timeout_lehnt_ab(scanner_konfiguriert):
    async with FakeClamd(b"stream: OK\0", verzoegerung=2.0) as clamd:
        scanner_konfiguriert(clamd.port, timeout=0.2)
        with pytest.raises(HTTPException) as fehler:
            await virenscan.pruefe_auf_schadsoftware(b"irgendwas", "datei.pdf")
    assert fehler.value.status_code == 503


@pytest.mark.asyncio
async def test_unverstaendliche_antwort_lehnt_ab(scanner_konfiguriert):
    """Kein 'OK' und kein 'FOUND' - im Zweifel nicht durchlassen."""
    async with FakeClamd(b"stream: ERROR beim Scannen\0") as clamd:
        scanner_konfiguriert(clamd.port)
        with pytest.raises(HTTPException) as fehler:
            await virenscan.pruefe_auf_schadsoftware(b"irgendwas", "datei.pdf")
    assert fehler.value.status_code == 503


# ---------------------------------------------------------------------------
# Zusammenspiel mit dem Upload-Pfad
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_infizierte_datei_landet_nicht_auf_der_platte(scanner_konfiguriert, tmp_path, monkeypatch):
    """Der Scan muss VOR dem Schreiben laufen - sonst liegt die Datei
    verschlüsselt auf der Platte und ist für einen dateibasierten Scan
    unsichtbar."""
    import io

    from fastapi import UploadFile

    from app.core import uploads

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    upload = UploadFile(filename="schad.pdf", file=io.BytesIO(b"%PDF-1.7 " + EICAR))

    async with FakeClamd(b"stream: Eicar-Signature FOUND\0") as clamd:
        scanner_konfiguriert(clamd.port)
        with pytest.raises(HTTPException) as fehler:
            await uploads.datei_speichern(upload, "bewerbungen/1")

    assert fehler.value.status_code == 400
    geschrieben = list(tmp_path.rglob("*.pdf"))
    assert geschrieben == [], f"Datei trotz Virenfund geschrieben: {geschrieben}"


@pytest.mark.asyncio
async def test_saubere_datei_wird_normal_gespeichert(scanner_konfiguriert, tmp_path, monkeypatch):
    import io

    from fastapi import UploadFile

    from app.core import uploads

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    upload = UploadFile(filename="lebenslauf.pdf", file=io.BytesIO(b"%PDF-1.7 sauber"))

    async with FakeClamd(b"stream: OK\0") as clamd:
        scanner_konfiguriert(clamd.port)
        name, pfad, groesse = await uploads.datei_speichern(upload, "bewerbungen/1")

    assert name == "lebenslauf.pdf"
    assert groesse == len(b"%PDF-1.7 sauber")
    gespeichert = (tmp_path / pfad).read_bytes()
    # Auf der Platte liegt Ciphertext, nicht der Klartext.
    assert gespeichert.startswith(b"gAAAAA")
