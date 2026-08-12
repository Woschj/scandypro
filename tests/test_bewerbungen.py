"""Tests für `app/routers/bewerbungen.py` (PR-006, zweiter Teil).

Bewerbungsdaten sind besondere Kategorien nach Art. 9 DSGVO (siehe
CLAUDE.md §3): Firmen, Absagen, Notizen wie "Zusage laut Anruf" - dazu
hochgeladene Lebensläufe und Zeugnisse. Der Router hat 18 Routen, von denen
viele eine ID aus der URL nehmen; jede davon ist ein möglicher IDOR.

Die Berechtigungstests in `test_berechtigungen.py` prüfen die
Zugriffs*schicht*. Hier geht es um die Routen darüber: Greift
`require_owner` wirklich auf jedem Endpunkt, oder wurde er irgendwo
vergessen?

Bewusst mitgetestet ist die dokumentierte Grenze, dass Berufstrainer:innen
auch **mit** Freigabe keine Dateien herunterladen können (siehe Docstring
von `teilnehmer_ansicht`) - eine stille Ausweitung dieser Grenze wäre eine
Datenschutz-Änderung, die auffallen soll.
"""
import io
import re
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel import select

from app.core.security import hash_password
from app.models.bewerbung import (
    Bewerbung,
    BewerbungsFreigabe,
    BewerbungsFreigabeUmfang,
    BewerbungsNotiz,
    BewerbungStatus,
)
from app.models.organisation import BerufstrainerZuordnung
from app.models.user import RoleEnum, User
from tests.conftest import login

FREMD_EMAIL = "fremde@test.local"
FREMD_PASSWORT = "fremdpass123"
TRAINER_EMAIL = "trainer@test.local"
TRAINER_PASSWORT = "trainerpass123"


async def _csrf_token(client: AsyncClient) -> str:
    seite = await client.get("/konto")
    treffer = re.search(r'name="csrf_token" value="([^"]+)"', seite.text)
    assert treffer, "csrf_token nicht gefunden"
    return treffer.group(1)


@pytest_asyncio.fixture
async def welt(session_maker, seed_data):
    """Owner (aus seed_data), eine fremde Teilnehmer:in, eine zugeordnete
    Berufstrainer:in - plus eine Bewerbung mit Notiz beim Owner."""
    async with session_maker() as session:
        fremd = User(
            name="Fremde Person",
            email=FREMD_EMAIL,
            password_hash=hash_password(FREMD_PASSWORT),
            role=RoleEnum.teilnehmer,
        )
        trainer = User(
            name="Test Trainer:in",
            email=TRAINER_EMAIL,
            password_hash=hash_password(TRAINER_PASSWORT),
            role=RoleEnum.berufstrainer,
        )
        session.add(fremd)
        session.add(trainer)
        await session.commit()
        await session.refresh(fremd)
        await session.refresh(trainer)

        session.add(
            BerufstrainerZuordnung(
                berufstrainer_id=trainer.id, teilnehmer_id=seed_data["teilnehmer_id"]
            )
        )
        bewerbung = Bewerbung(
            teilnehmer_id=seed_data["teilnehmer_id"],
            firma="Musterfirma",
            position="Testposition",
            status=BewerbungStatus.versendet,
        )
        session.add(bewerbung)
        await session.commit()
        await session.refresh(bewerbung)

        notiz = BewerbungsNotiz(bewerbung_id=bewerbung.id, text="Telefonat gefuehrt")
        session.add(notiz)
        await session.commit()
        await session.refresh(notiz)

        return {
            **seed_data,
            "fremd_id": fremd.id,
            "trainer_id": trainer.id,
            "bewerbung_id": bewerbung.id,
            "notiz_id": notiz.id,
        }


# ---------------------------------------------------------------------------
# Eigene Daten
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_sieht_eigene_bewerbung(client: AsyncClient, welt):
    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    antwort = await client.get("/bewerbungen")
    assert antwort.status_code == 200
    assert "Musterfirma" in antwort.text


@pytest.mark.asyncio
async def test_verschluesselte_notiz_wird_im_klartext_angezeigt(client: AsyncClient, welt):
    """Belegt, dass der VerschluesselterText-TypeDecorator beim Lesen
    tatsächlich entschlüsselt - sonst stünde hier Ciphertext."""
    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    antwort = await client.get("/bewerbungen")
    assert "Telefonat gefuehrt" in antwort.text
    assert "gAAAAA" not in antwort.text


# ---------------------------------------------------------------------------
# IDOR: fremde Teilnehmer:in auf jedem ID-nehmenden Endpunkt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fremde_person_sieht_bewerbung_nicht_in_der_liste(client: AsyncClient, welt):
    await login(client, FREMD_EMAIL, FREMD_PASSWORT)
    antwort = await client.get("/bewerbungen")
    assert antwort.status_code == 200
    assert "Musterfirma" not in antwort.text


@pytest.mark.asyncio
async def test_fremde_person_kommt_an_keinen_bewerbungs_endpunkt(client: AsyncClient, welt):
    """Jede Route, die eine Bewerbungs-ID aus der URL nimmt, muss blocken."""
    await login(client, FREMD_EMAIL, FREMD_PASSWORT)
    token = await _csrf_token(client)
    bid = welt["bewerbung_id"]

    posts = [
        (f"/bewerbungen/{bid}/status", {"status_wert": "abgesagt"}),
        (f"/bewerbungen/{bid}/notizen", {"text": "eingeschmuggelt"}),
        (f"/bewerbungen/{bid}/loeschen", {}),
        (f"/bewerbungen/notizen/{welt['notiz_id']}/loeschen", {}),
    ]
    for pfad, daten in posts:
        antwort = await client.post(pfad, data={"csrf_token": token, **daten})
        assert antwort.status_code == 403, f"{pfad} war fuer eine fremde Person erreichbar"

    for pfad in (f"/bewerbungen/{bid}/pdf",):
        antwort = await client.get(pfad)
        assert antwort.status_code == 403, f"{pfad} war fuer eine fremde Person erreichbar"


@pytest.mark.asyncio
async def test_fremde_person_aendert_status_nicht(client: AsyncClient, session_maker, welt):
    await login(client, FREMD_EMAIL, FREMD_PASSWORT)
    await client.post(
        f"/bewerbungen/{welt['bewerbung_id']}/status",
        data={"csrf_token": await _csrf_token(client), "status_wert": "abgesagt"},
    )
    async with session_maker() as session:
        bewerbung = await session.get(Bewerbung, welt["bewerbung_id"])
        assert bewerbung.status == BewerbungStatus.versendet


@pytest.mark.asyncio
async def test_fremde_person_loescht_notiz_nicht(client: AsyncClient, session_maker, welt):
    await login(client, FREMD_EMAIL, FREMD_PASSWORT)
    await client.post(
        f"/bewerbungen/notizen/{welt['notiz_id']}/loeschen",
        data={"csrf_token": await _csrf_token(client)},
    )
    async with session_maker() as session:
        assert await session.get(BewerbungsNotiz, welt["notiz_id"]) is not None


# ---------------------------------------------------------------------------
# Datei-Upload und -Download
# ---------------------------------------------------------------------------


async def _lade_unterlage_hoch(client: AsyncClient, bewerbung_id: int) -> None:
    """Lädt ein Anschreiben zu einer konkreten Bewerbung hoch.

    Bewusst dieser Endpunkt und nicht /bewerbungen/unterlagen: letzterer
    legt Stammunterlagen an, die keiner einzelnen Bewerbung gehören und
    beim Löschen einer Bewerbung deshalb auch nicht mitgehen sollen.
    """
    antwort = await client.post(
        f"/bewerbungen/{bewerbung_id}/anschreiben",
        data={"csrf_token": await _csrf_token(client)},
        files={"datei": ("anschreiben.pdf", io.BytesIO(b"%PDF-1.7 mein Anschreiben"), "application/pdf")},
        follow_redirects=False,
    )
    assert antwort.status_code == 303, antwort.text


@pytest.mark.asyncio
async def test_owner_laedt_hoch_und_wieder_herunter(client: AsyncClient, session_maker, welt):
    from app.models.bewerbung import Bewerbungsunterlage

    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    await _lade_unterlage_hoch(client, welt["bewerbung_id"])

    async with session_maker() as session:
        ergebnis = await session.execute(select(Bewerbungsunterlage))
        unterlage = ergebnis.scalars().one()

    antwort = await client.get(f"/bewerbungen/unterlagen/{unterlage.id}/download")
    assert antwort.status_code == 200
    # Entschlüsselt zurück, nicht der Ciphertext von der Platte.
    assert antwort.content == b"%PDF-1.7 mein Anschreiben"


@pytest.mark.asyncio
async def test_fremde_person_laedt_datei_nicht_herunter(client: AsyncClient, session_maker, welt):
    from app.models.bewerbung import Bewerbungsunterlage

    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    await _lade_unterlage_hoch(client, welt["bewerbung_id"])
    async with session_maker() as session:
        unterlage = (await session.execute(select(Bewerbungsunterlage))).scalars().one()

    await login(client, FREMD_EMAIL, FREMD_PASSWORT)
    antwort = await client.get(f"/bewerbungen/unterlagen/{unterlage.id}/download")
    assert antwort.status_code == 403


@pytest.mark.asyncio
async def test_trainer_laedt_datei_auch_mit_freigabe_nicht_herunter(
    client: AsyncClient, session_maker, welt
):
    """Dokumentierte Grenze: die Freigabe öffnet die Metadaten-Ansicht, nicht
    die Dateien (siehe Docstring von teilnehmer_ansicht). Wenn dieser Test
    fällt, wurde der Zugriff ausgeweitet - das ist eine
    Datenschutz-Entscheidung und darf nicht nebenbei passieren."""
    from app.models.bewerbung import Bewerbungsunterlage

    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    await _lade_unterlage_hoch(client, welt["bewerbung_id"])
    async with session_maker() as session:
        unterlage = (await session.execute(select(Bewerbungsunterlage))).scalars().one()
        session.add(
            BewerbungsFreigabe(
                teilnehmer_id=welt["teilnehmer_id"],
                empfaenger_id=welt["trainer_id"],
                umfang=BewerbungsFreigabeUmfang.alle,
            )
        )
        await session.commit()

    await login(client, TRAINER_EMAIL, TRAINER_PASSWORT)
    # Metadaten-Ansicht ist offen …
    ansicht = await client.get(f"/bewerbungen/teilnehmer/{welt['teilnehmer_id']}")
    assert ansicht.status_code == 200
    # … die Datei nicht.
    antwort = await client.get(f"/bewerbungen/unterlagen/{unterlage.id}/download")
    assert antwort.status_code == 403


@pytest.mark.asyncio
async def test_loeschen_entfernt_auch_die_datei_von_der_platte(
    client: AsyncClient, session_maker, welt
):
    from app.core.uploads import voller_pfad
    from app.models.bewerbung import Bewerbungsunterlage

    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    await _lade_unterlage_hoch(client, welt["bewerbung_id"])
    async with session_maker() as session:
        unterlage = (await session.execute(select(Bewerbungsunterlage))).scalars().one()
        pfad = voller_pfad(unterlage.speicherpfad)
    assert pfad.exists()

    await client.post(
        f"/bewerbungen/{welt['bewerbung_id']}/loeschen",
        data={"csrf_token": await _csrf_token(client)},
        follow_redirects=False,
    )
    assert not pfad.exists(), "verschluesselte Datei blieb nach dem Loeschen liegen"


# ---------------------------------------------------------------------------
# Trainer-Ansicht: Zuordnung UND Freigabe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trainer_ohne_freigabe_sieht_nichts(client: AsyncClient, welt):
    """Zuordnung allein reicht nicht."""
    await login(client, TRAINER_EMAIL, TRAINER_PASSWORT)
    antwort = await client.get(f"/bewerbungen/teilnehmer/{welt['teilnehmer_id']}")
    assert antwort.status_code == 403


@pytest.mark.asyncio
async def test_trainer_ohne_zuordnung_sieht_nichts(client: AsyncClient, session_maker, welt):
    """Freigabe allein reicht auch nicht - beides muss zusammenkommen."""
    async with session_maker() as session:
        ohne_zuordnung = User(
            name="Fremde Trainer:in",
            email="trainer2@test.local",
            password_hash=hash_password("trainerpass123"),
            role=RoleEnum.berufstrainer,
        )
        session.add(ohne_zuordnung)
        await session.commit()
        await session.refresh(ohne_zuordnung)
        session.add(
            BewerbungsFreigabe(
                teilnehmer_id=welt["teilnehmer_id"],
                empfaenger_id=ohne_zuordnung.id,
                umfang=BewerbungsFreigabeUmfang.alle,
            )
        )
        await session.commit()

    await login(client, "trainer2@test.local", "trainerpass123")
    antwort = await client.get(f"/bewerbungen/teilnehmer/{welt['teilnehmer_id']}")
    assert antwort.status_code == 403


@pytest.mark.asyncio
async def test_abgelaufene_freigabe_greift_nicht_mehr(client: AsyncClient, session_maker, welt):
    async with session_maker() as session:
        session.add(
            BewerbungsFreigabe(
                teilnehmer_id=welt["teilnehmer_id"],
                empfaenger_id=welt["trainer_id"],
                umfang=BewerbungsFreigabeUmfang.alle,
                gueltig_bis=date.today() - timedelta(days=1),
            )
        )
        await session.commit()

    await login(client, TRAINER_EMAIL, TRAINER_PASSWORT)
    antwort = await client.get(f"/bewerbungen/teilnehmer/{welt['teilnehmer_id']}")
    assert antwort.status_code == 403


@pytest.mark.asyncio
async def test_widerruf_wirkt_sofort(client: AsyncClient, session_maker, welt):
    async with session_maker() as session:
        freigabe = BewerbungsFreigabe(
            teilnehmer_id=welt["teilnehmer_id"],
            empfaenger_id=welt["trainer_id"],
            umfang=BewerbungsFreigabeUmfang.alle,
        )
        session.add(freigabe)
        await session.commit()
        await session.refresh(freigabe)
        freigabe_id = freigabe.id

    await login(client, TRAINER_EMAIL, TRAINER_PASSWORT)
    assert (await client.get(f"/bewerbungen/teilnehmer/{welt['teilnehmer_id']}")).status_code == 200

    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    await client.post(
        f"/bewerbungen/freigaben/{freigabe_id}/widerrufen",
        data={"csrf_token": await _csrf_token(client)},
        follow_redirects=False,
    )

    await login(client, TRAINER_EMAIL, TRAINER_PASSWORT)
    assert (await client.get(f"/bewerbungen/teilnehmer/{welt['teilnehmer_id']}")).status_code == 403


@pytest.mark.asyncio
async def test_teilnehmer_kann_fremde_freigabe_nicht_widerrufen(
    client: AsyncClient, session_maker, welt
):
    async with session_maker() as session:
        freigabe = BewerbungsFreigabe(
            teilnehmer_id=welt["teilnehmer_id"],
            empfaenger_id=welt["trainer_id"],
            umfang=BewerbungsFreigabeUmfang.alle,
        )
        session.add(freigabe)
        await session.commit()
        await session.refresh(freigabe)
        freigabe_id = freigabe.id

    await login(client, FREMD_EMAIL, FREMD_PASSWORT)
    antwort = await client.post(
        f"/bewerbungen/freigaben/{freigabe_id}/widerrufen",
        data={"csrf_token": await _csrf_token(client)},
    )
    assert antwort.status_code == 403

    async with session_maker() as session:
        unveraendert = await session.get(BewerbungsFreigabe, freigabe_id)
        assert unveraendert.widerrufen_am is None
