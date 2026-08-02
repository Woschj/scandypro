"""CSRF-Absicherung (siehe app/core/deps.py:verify_csrf, app/core/security.py):
POST ohne oder mit falschem Token wird abgelehnt, mit korrektem Token (Formularfeld
oder X-CSRF-Token-Header für fetch()-Requests) geht die Anfrage durch."""
import re

import pytest
from httpx import AsyncClient

from tests.conftest import login


@pytest.mark.asyncio
async def test_post_ohne_csrf_token_wird_abgelehnt(client: AsyncClient, seed_data):
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    resp = await client.post("/konto/passwort", data={
        "aktuelles_passwort": seed_data["teilnehmer_passwort"],
        "neues_passwort": "neuespasswort123",
        "neues_passwort_wiederholen": "neuespasswort123",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_mit_falschem_csrf_token_wird_abgelehnt(client: AsyncClient, seed_data):
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    resp = await client.post("/konto/passwort", data={
        "csrf_token": "definitiv-falsch",
        "aktuelles_passwort": seed_data["teilnehmer_passwort"],
        "neues_passwort": "neuespasswort123",
        "neues_passwort_wiederholen": "neuespasswort123",
    })
    assert resp.status_code == 403


def _csrf_token_aus_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "csrf_token-Feld nicht im Formular gefunden"
    return match.group(1)


@pytest.mark.asyncio
async def test_post_mit_korrektem_csrf_token_geht_durch(client: AsyncClient, seed_data):
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    konto_seite = await client.get("/konto")
    token = _csrf_token_aus_html(konto_seite.text)

    resp = await client.post("/konto/passwort", data={
        "csrf_token": token,
        "aktuelles_passwort": seed_data["teilnehmer_passwort"],
        "neues_passwort": "neuespasswort123",
        "neues_passwort_wiederholen": "neuespasswort123",
    })
    assert resp.status_code == 200
    assert "form-success" in resp.text


@pytest.mark.asyncio
async def test_json_post_mit_csrf_header_geht_durch(client: AsyncClient, seed_data):
    """Deckt den fetch()-Pfad ab (app/static/js/wohlbefinden.js): JSON-Body,
    Token im X-CSRF-Token-Header statt im Formularfeld."""
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    konto_seite = await client.get("/konto")
    token = _csrf_token_aus_html(konto_seite.text)

    resp = await client.post(
        "/wohlbefinden/tag",
        json={"datum": "2026-01-05", "stimmung": 7, "belastbarkeit": 6},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_json_post_ohne_csrf_header_wird_abgelehnt(client: AsyncClient, seed_data):
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    resp = await client.post(
        "/wohlbefinden/tag",
        json={"datum": "2026-01-05", "stimmung": 7, "belastbarkeit": 6},
    )
    assert resp.status_code == 403
