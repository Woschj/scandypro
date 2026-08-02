"""Smoke-Test für das Test-Scaffolding selbst (siehe conftest.py) - prüft
den Login-Grundfluss, der von den meisten künftigen Tests als Baustein
gebraucht wird."""
from tests.conftest import login


async def test_unauthenticated_redirect_to_login(client):
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


async def test_login_success(client, seed_data):
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code == 200
    assert seed_data["teilnehmer_id"]


async def test_login_falsches_passwort(client, seed_data):
    resp = await client.post(
        "/login", data={"email": seed_data["teilnehmer_email"], "password": "falsch"}
    )
    assert resp.status_code == 401
    assert "falsch" in resp.text.lower()
