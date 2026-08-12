"""Tests für `app/routers/wochenberichte.py` (PR-006, dritter Teil).

Der interessante Teil ist hier die **statusabhängige** Sichtbarkeit: Ein
Wochenbericht im Entwurf gehört ausschließlich der Person, die ihn
schreibt. Erst mit dem Abgeben wird er für die Leitung des Handlungsfelds
sichtbar - und mit dem Zurückziehen wieder unsichtbar.

Das ist eine bewusste Zusage an die Teilnehmer:innen ("solange du daran
arbeitest, liest niemand mit"). Ein Fehler an dieser Stelle bricht kein
Gesetz, aber ein Versprechen - und würde vermutlich nie auffallen, weil
niemand von außen sieht, wer wann was gelesen hat.
"""
import re

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.security import hash_password
from app.models.organisation import (
    Handlungsfeld,
    HandlungsfeldLeitung,
    Teilnehmergruppe,
    TeilnehmergruppeMitglied,
)
from app.models.user import RoleEnum, User
from app.models.wochenbericht import Wochenbericht, WochenberichtStatus, leere_tage
from tests.conftest import login

TRAINER_EMAIL = "leitung@test.local"
TRAINER_PASSWORT = "leitungpass123"
FREMD_TRAINER_EMAIL = "fremdleitung@test.local"
FREMD_TRAINER_PASSWORT = "fremdpass123"
ZWEITE_EMAIL = "zweite@test.local"
ZWEITE_PASSWORT = "zweitepass123"


async def _csrf_token(client: AsyncClient) -> str:
    seite = await client.get("/konto")
    treffer = re.search(r'name="csrf_token" value="([^"]+)"', seite.text)
    assert treffer
    return treffer.group(1)


@pytest_asyncio.fixture
async def welt(session_maker, seed_data):
    """Teilnehmer:in in einer Gruppe eines Handlungsfelds mit Leitung, plus
    eine unbeteiligte Trainer:in und eine zweite Teilnehmer:in."""
    async with session_maker() as session:
        leitung = User(
            name="Leitende Trainer:in",
            email=TRAINER_EMAIL,
            password_hash=hash_password(TRAINER_PASSWORT),
            role=RoleEnum.berufstrainer,
        )
        fremd_leitung = User(
            name="Andere Trainer:in",
            email=FREMD_TRAINER_EMAIL,
            password_hash=hash_password(FREMD_TRAINER_PASSWORT),
            role=RoleEnum.berufstrainer,
        )
        zweite = User(
            name="Zweite Teilnehmer:in",
            email=ZWEITE_EMAIL,
            password_hash=hash_password(ZWEITE_PASSWORT),
            role=RoleEnum.teilnehmer,
        )
        session.add_all([leitung, fremd_leitung, zweite])
        await session.commit()
        for u in (leitung, fremd_leitung, zweite):
            await session.refresh(u)

        handlungsfeld = Handlungsfeld(name="Video-Projekte", abteilung_id=seed_data["abteilung_id"])
        session.add(handlungsfeld)
        await session.commit()
        await session.refresh(handlungsfeld)

        gruppe = Teilnehmergruppe(
            name="Projektteam", handlungsfeld_id=handlungsfeld.id, erstellt_von=leitung.id
        )
        session.add(gruppe)
        session.add(
            HandlungsfeldLeitung(handlungsfeld_id=handlungsfeld.id, berufstrainer_id=leitung.id)
        )
        await session.commit()
        await session.refresh(gruppe)

        session.add(
            TeilnehmergruppeMitglied(
                gruppe_id=gruppe.id, teilnehmer_id=seed_data["teilnehmer_id"]
            )
        )

        bericht = Wochenbericht(
            teilnehmer_id=seed_data["teilnehmer_id"],
            kw_jahr=2026,
            kw_nummer=33,
            tage={**leere_tage(), "montag": {"start": "08:00", "ende": "16:00",
                                             "taetigkeiten": "Kamera aufgebaut"}},
            status=WochenberichtStatus.entwurf,
        )
        session.add(bericht)
        await session.commit()
        await session.refresh(bericht)

        return {
            **seed_data,
            "leitung_id": leitung.id,
            "zweite_id": zweite.id,
            "bericht_id": bericht.id,
        }


async def _bericht(session_maker, bericht_id: int) -> Wochenbericht:
    async with session_maker() as session:
        return await session.get(Wochenbericht, bericht_id)


# ---------------------------------------------------------------------------
# Entwurf ist privat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_sieht_eigenen_entwurf(client: AsyncClient, welt):
    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    antwort = await client.get("/wochenberichte")
    assert antwort.status_code == 200
    assert "Kamera aufgebaut" in antwort.text


@pytest.mark.asyncio
async def test_leitung_sieht_entwurf_nicht(client: AsyncClient, welt):
    """Der Kern der Zusage: solange der Bericht Entwurf ist, liest niemand
    mit - auch nicht die zuständige Leitung."""
    await login(client, TRAINER_EMAIL, TRAINER_PASSWORT)
    antwort = await client.get("/wochenberichte")
    assert antwort.status_code == 200
    assert "Kamera aufgebaut" not in antwort.text


@pytest.mark.asyncio
async def test_zweite_teilnehmerin_sieht_fremden_bericht_nicht(client: AsyncClient, welt):
    await login(client, ZWEITE_EMAIL, ZWEITE_PASSWORT)
    antwort = await client.get("/wochenberichte")
    assert "Kamera aufgebaut" not in antwort.text


# ---------------------------------------------------------------------------
# Abgeben macht sichtbar, Zurückziehen wieder unsichtbar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nach_abgabe_sieht_die_leitung_den_bericht(client: AsyncClient, session_maker, welt):
    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    antwort = await client.post(
        f"/wochenberichte/{welt['bericht_id']}/abgeben",
        data={"csrf_token": await _csrf_token(client)},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    assert (await _bericht(session_maker, welt["bericht_id"])).status == WochenberichtStatus.abgegeben

    await login(client, TRAINER_EMAIL, TRAINER_PASSWORT)
    ansicht = await client.get("/wochenberichte")
    assert "Kamera aufgebaut" in ansicht.text


@pytest.mark.asyncio
async def test_zurueckziehen_nimmt_die_sichtbarkeit_wieder(client: AsyncClient, welt):
    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    token = await _csrf_token(client)
    await client.post(
        f"/wochenberichte/{welt['bericht_id']}/abgeben",
        data={"csrf_token": token}, follow_redirects=False,
    )
    await client.post(
        f"/wochenberichte/{welt['bericht_id']}/zurueckziehen",
        data={"csrf_token": token}, follow_redirects=False,
    )

    await login(client, TRAINER_EMAIL, TRAINER_PASSWORT)
    ansicht = await client.get("/wochenberichte")
    assert "Kamera aufgebaut" not in ansicht.text


@pytest.mark.asyncio
async def test_fremde_leitung_sieht_auch_abgegebenen_bericht_nicht(
    client: AsyncClient, welt
):
    """Abgeben öffnet den Bericht für die Leitung des *eigenen*
    Handlungsfelds, nicht für Trainer:innen allgemein."""
    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    await client.post(
        f"/wochenberichte/{welt['bericht_id']}/abgeben",
        data={"csrf_token": await _csrf_token(client)}, follow_redirects=False,
    )

    await login(client, FREMD_TRAINER_EMAIL, FREMD_TRAINER_PASSWORT)
    ansicht = await client.get("/wochenberichte")
    assert "Kamera aufgebaut" not in ansicht.text


# ---------------------------------------------------------------------------
# Fremdzugriff auf die ID-nehmenden Endpunkte
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fremde_person_kommt_an_keinen_bericht_endpunkt(client: AsyncClient, welt):
    await login(client, ZWEITE_EMAIL, ZWEITE_PASSWORT)
    token = await _csrf_token(client)
    bid = welt["bericht_id"]

    for pfad in (
        f"/wochenberichte/{bid}/abgeben",
        f"/wochenberichte/{bid}/zurueckziehen",
        f"/wochenberichte/{bid}/loeschen",
    ):
        antwort = await client.post(pfad, data={"csrf_token": token})
        assert antwort.status_code == 403, f"{pfad} war fuer eine fremde Person erreichbar"

    antwort = await client.get(f"/wochenberichte/{bid}/word")
    assert antwort.status_code == 403, "Word-Export war fuer eine fremde Person erreichbar"


@pytest.mark.asyncio
async def test_leitung_kann_fremden_bericht_nicht_abgeben(client: AsyncClient, session_maker, welt):
    """Auch die zuständige Leitung darf nicht *für* jemanden abgeben - das
    wäre eine Erklärung im fremden Namen."""
    await login(client, TRAINER_EMAIL, TRAINER_PASSWORT)
    antwort = await client.post(
        f"/wochenberichte/{welt['bericht_id']}/abgeben",
        data={"csrf_token": await _csrf_token(client)},
    )
    assert antwort.status_code == 403
    assert (await _bericht(session_maker, welt["bericht_id"])).status == WochenberichtStatus.entwurf


# ---------------------------------------------------------------------------
# Statusregeln
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abgegebener_bericht_laesst_sich_nicht_loeschen(
    client: AsyncClient, session_maker, welt
):
    """Sonst könnte man eine bereits abgegebene Erklärung nachträglich
    spurlos entfernen."""
    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    token = await _csrf_token(client)
    await client.post(
        f"/wochenberichte/{welt['bericht_id']}/abgeben",
        data={"csrf_token": token}, follow_redirects=False,
    )

    antwort = await client.post(
        f"/wochenberichte/{welt['bericht_id']}/loeschen", data={"csrf_token": token}
    )
    assert antwort.status_code == 400
    assert await _bericht(session_maker, welt["bericht_id"]) is not None


@pytest.mark.asyncio
async def test_entwurf_laesst_sich_nicht_zurueckziehen(client: AsyncClient, welt):
    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    antwort = await client.post(
        f"/wochenberichte/{welt['bericht_id']}/zurueckziehen",
        data={"csrf_token": await _csrf_token(client)},
    )
    assert antwort.status_code == 400


@pytest.mark.asyncio
async def test_owner_loescht_eigenen_entwurf(client: AsyncClient, session_maker, welt):
    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    antwort = await client.post(
        f"/wochenberichte/{welt['bericht_id']}/loeschen",
        data={"csrf_token": await _csrf_token(client)},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    assert await _bericht(session_maker, welt["bericht_id"]) is None


@pytest.mark.asyncio
async def test_word_export_fuer_owner(client: AsyncClient, welt):
    await login(client, welt["teilnehmer_email"], welt["teilnehmer_passwort"])
    antwort = await client.get(f"/wochenberichte/{welt['bericht_id']}/word")
    assert antwort.status_code == 200
    # .docx ist ein ZIP-Container - erkennbar an der PK-Signatur.
    assert antwort.content[:2] == b"PK"
