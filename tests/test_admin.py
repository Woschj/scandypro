"""Tests für die Benutzerverwaltung in `app/routers/admin.py` (PR-006).

Von allen ungetesteten Routern war dieser der heikelste: hier werden Rollen
vergeben, Accounts gesperrt und Passwörter zurückgesetzt. Ein Fehler an
dieser Stelle vergibt Zugriff auf Gesundheits- und Bewerbungsdaten, ohne
dass irgendwo eine Freigabe erteilt wurde - die sorgfältig getestete
Zugriffsschicht (siehe test_berechtigungen.py) hilft dann nichts mehr, weil
sie die Rolle als gegeben hinnimmt.

Schwerpunkt liegt deshalb auf den Fällen, die *nicht* passieren dürfen:
Nicht-Admins kommen nicht rein, niemand hebt seine eigene Rolle an, niemand
sperrt sich selbst aus, und ein Passwort-Reset erzeugt wirklich einen neuen
gültigen Hash statt still nichts zu tun.
"""
import re

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel import select

from app.core.security import hash_password, verify_password
from app.models.user import RoleEnum, User
from tests.conftest import login

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORT = "adminpass123"


async def _csrf_token(client: AsyncClient) -> str:
    seite = await client.get("/konto")
    match = re.search(r'name="csrf_token" value="([^"]+)"', seite.text)
    assert match, "csrf_token nicht gefunden"
    return match.group(1)


@pytest_asyncio.fixture
async def admin_welt(session_maker, seed_data):
    """Admin + Berufstrainer:in zusätzlich zur Teilnehmer:in aus seed_data."""
    async with session_maker() as session:
        admin = User(
            name="Test Admin",
            email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORT),
            role=RoleEnum.einrichtungs_admin,
        )
        trainer = User(
            name="Test Trainer:in",
            email="trainer@test.local",
            password_hash=hash_password("trainerpass123"),
            role=RoleEnum.berufstrainer,
        )
        session.add(admin)
        session.add(trainer)
        await session.commit()
        await session.refresh(admin)
        await session.refresh(trainer)

        return {
            **seed_data,
            "admin_id": admin.id,
            "admin_email": ADMIN_EMAIL,
            "admin_passwort": ADMIN_PASSWORT,
            "trainer_id": trainer.id,
        }


async def _benutzer(session_maker, benutzer_id: int) -> User:
    async with session_maker() as session:
        result = await session.execute(select(User).where(User.id == benutzer_id))
        return result.scalars().one()


# ---------------------------------------------------------------------------
# Zugang zur Verwaltung überhaupt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pfad",
    ["/admin/benutzer", "/admin/abteilungen", "/admin/psm-zuordnungen", "/admin/trainer-zuordnungen"],
)
async def test_teilnehmer_kommt_nicht_in_die_verwaltung(client: AsyncClient, admin_welt, pfad):
    """Der wichtigste Negativfall: eine Teilnehmer:in darf keine einzige
    Verwaltungsseite sehen - dort stehen alle Namen und E-Mail-Adressen der
    Einrichtung."""
    await login(client, admin_welt["teilnehmer_email"], admin_welt["teilnehmer_passwort"])
    antwort = await client.get(pfad)
    assert antwort.status_code == 403, f"{pfad} war für eine Teilnehmer:in erreichbar"


@pytest.mark.asyncio
async def test_berufstrainer_kommt_nicht_in_die_benutzerverwaltung(client: AsyncClient, admin_welt):
    """Auch eine Rolle mit erweiterten Rechten ist noch lange keine
    Verwaltung - Trainer:innen dürfen keine Accounts anlegen."""
    await login(client, "trainer@test.local", "trainerpass123")
    antwort = await client.get("/admin/benutzer")
    assert antwort.status_code == 403


@pytest.mark.asyncio
async def test_ohne_login_kein_zugriff(client: AsyncClient, admin_welt):
    antwort = await client.get("/admin/benutzer", follow_redirects=False)
    assert antwort.status_code in (303, 401)


@pytest.mark.asyncio
async def test_admin_sieht_benutzeruebersicht(client: AsyncClient, admin_welt):
    await login(client, admin_welt["admin_email"], admin_welt["admin_passwort"])
    antwort = await client.get("/admin/benutzer")
    assert antwort.status_code == 200
    assert "Test Teilnehmer:in" in antwort.text


# ---------------------------------------------------------------------------
# Account anlegen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_legt_account_an(client: AsyncClient, session_maker, admin_welt):
    await login(client, admin_welt["admin_email"], admin_welt["admin_passwort"])
    antwort = await client.post(
        "/admin/benutzer",
        data={
            "csrf_token": await _csrf_token(client),
            "name": "Neue Person",
            "email": "Neue.Person@Test.Local",
            "passwort": "sicheres-passwort",
            "rolle": RoleEnum.teilnehmer.value,
        },
        follow_redirects=False,
    )
    assert antwort.status_code == 303

    async with session_maker() as session:
        result = await session.execute(select(User).where(User.name == "Neue Person"))
        neuer = result.scalars().one()
    # E-Mail wird normalisiert gespeichert, sonst gäbe es "a@x" und "A@X"
    # als zwei Accounts und der Login-Lookup fände je nach Schreibweise
    # einen anderen.
    assert neuer.email == "neue.person@test.local"
    assert neuer.role == RoleEnum.teilnehmer
    assert neuer.password_hash != "sicheres-passwort"
    assert verify_password("sicheres-passwort", neuer.password_hash)


@pytest.mark.asyncio
async def test_zu_kurzes_passwort_wird_abgelehnt(client: AsyncClient, session_maker, admin_welt):
    await login(client, admin_welt["admin_email"], admin_welt["admin_passwort"])
    antwort = await client.post(
        "/admin/benutzer",
        data={
            "csrf_token": await _csrf_token(client),
            "name": "Zu Kurz",
            "email": "kurz@test.local",
            "passwort": "1234567",
            "rolle": RoleEnum.teilnehmer.value,
        },
    )
    assert antwort.status_code == 400

    async with session_maker() as session:
        result = await session.execute(select(User).where(User.email == "kurz@test.local"))
        assert result.first() is None, "Account trotz abgelehntem Passwort angelegt"


@pytest.mark.asyncio
async def test_doppelte_email_wird_abgelehnt(client: AsyncClient, session_maker, admin_welt):
    """Zwei Accounts mit derselben E-Mail würden den Login mehrdeutig machen."""
    await login(client, admin_welt["admin_email"], admin_welt["admin_passwort"])
    antwort = await client.post(
        "/admin/benutzer",
        data={
            "csrf_token": await _csrf_token(client),
            "name": "Doppelgänger",
            # Bewusst andere Schreibweise: die Prüfung muss nach der
            # Normalisierung greifen, nicht davor.
            "email": admin_welt["teilnehmer_email"].upper(),
            "passwort": "sicheres-passwort",
            "rolle": RoleEnum.teilnehmer.value,
        },
    )
    assert antwort.status_code == 400

    async with session_maker() as session:
        result = await session.execute(
            select(User).where(User.email == admin_welt["teilnehmer_email"])
        )
        assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_teilnehmer_kann_keinen_account_anlegen(client: AsyncClient, session_maker, admin_welt):
    """Der gefährlichste denkbare Fall: eine Teilnehmer:in legt sich selbst
    einen Admin-Account an."""
    await login(client, admin_welt["teilnehmer_email"], admin_welt["teilnehmer_passwort"])
    antwort = await client.post(
        "/admin/benutzer",
        data={
            "csrf_token": await _csrf_token(client),
            "name": "Heimlicher Admin",
            "email": "heimlich@test.local",
            "passwort": "sicheres-passwort",
            "rolle": RoleEnum.einrichtungs_admin.value,
        },
    )
    assert antwort.status_code == 403

    async with session_maker() as session:
        result = await session.execute(select(User).where(User.email == "heimlich@test.local"))
        assert result.first() is None


# ---------------------------------------------------------------------------
# Rollen ändern
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_aendert_fremde_rolle(client: AsyncClient, session_maker, admin_welt):
    await login(client, admin_welt["admin_email"], admin_welt["admin_passwort"])
    antwort = await client.post(
        f"/admin/benutzer/{admin_welt['teilnehmer_id']}/bearbeiten",
        data={
            "csrf_token": await _csrf_token(client),
            "name": "Test Teilnehmer:in",
            "email": admin_welt["teilnehmer_email"],
            "rolle": RoleEnum.berufstrainer.value,
        },
        follow_redirects=False,
    )
    assert antwort.status_code == 303

    geaendert = await _benutzer(session_maker, admin_welt["teilnehmer_id"])
    assert geaendert.role == RoleEnum.berufstrainer


@pytest.mark.asyncio
async def test_admin_kann_eigene_rolle_nicht_aendern(client: AsyncClient, session_maker, admin_welt):
    """Schutz gegen das versehentliche Aussperren der letzten Verwaltung -
    ohne Admin-Rolle käme niemand mehr an die Benutzerverwaltung."""
    await login(client, admin_welt["admin_email"], admin_welt["admin_passwort"])
    antwort = await client.post(
        f"/admin/benutzer/{admin_welt['admin_id']}/bearbeiten",
        data={
            "csrf_token": await _csrf_token(client),
            "name": "Test Admin",
            "email": ADMIN_EMAIL,
            "rolle": RoleEnum.teilnehmer.value,
        },
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    assert "fehler=" in antwort.headers["location"]

    unveraendert = await _benutzer(session_maker, admin_welt["admin_id"])
    assert unveraendert.role == RoleEnum.einrichtungs_admin


@pytest.mark.asyncio
async def test_teilnehmer_kann_sich_nicht_selbst_befoerdern(client: AsyncClient, session_maker, admin_welt):
    await login(client, admin_welt["teilnehmer_email"], admin_welt["teilnehmer_passwort"])
    antwort = await client.post(
        f"/admin/benutzer/{admin_welt['teilnehmer_id']}/bearbeiten",
        data={
            "csrf_token": await _csrf_token(client),
            "name": "Test Teilnehmer:in",
            "email": admin_welt["teilnehmer_email"],
            "rolle": RoleEnum.einrichtungs_admin.value,
        },
    )
    assert antwort.status_code == 403

    unveraendert = await _benutzer(session_maker, admin_welt["teilnehmer_id"])
    assert unveraendert.role == RoleEnum.teilnehmer


# ---------------------------------------------------------------------------
# Konto sperren
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_sperrt_und_entsperrt_konto(client: AsyncClient, session_maker, admin_welt):
    await login(client, admin_welt["admin_email"], admin_welt["admin_passwort"])
    token = await _csrf_token(client)

    await client.post(
        f"/admin/benutzer/{admin_welt['teilnehmer_id']}/aktiv-umschalten",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert (await _benutzer(session_maker, admin_welt["teilnehmer_id"])).aktiv is False

    await client.post(
        f"/admin/benutzer/{admin_welt['teilnehmer_id']}/aktiv-umschalten",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert (await _benutzer(session_maker, admin_welt["teilnehmer_id"])).aktiv is True


@pytest.mark.asyncio
async def test_gesperrtes_konto_kann_sich_nicht_anmelden(client: AsyncClient, session_maker, admin_welt):
    """Die Sperre muss den Login wirklich blockieren, nicht nur ein Flag
    setzen - genau hier lag der Fehler aus 0.1.42 (Dashboard prüfte `aktiv`
    nicht)."""
    await login(client, admin_welt["admin_email"], admin_welt["admin_passwort"])
    await client.post(
        f"/admin/benutzer/{admin_welt['teilnehmer_id']}/aktiv-umschalten",
        data={"csrf_token": await _csrf_token(client)},
        follow_redirects=False,
    )
    await client.post("/logout", data={"csrf_token": await _csrf_token(client)})

    antwort = await client.post(
        "/login",
        data={"email": admin_welt["teilnehmer_email"], "password": admin_welt["teilnehmer_passwort"]},
        follow_redirects=False,
    )
    assert antwort.status_code != 303, "Gesperrter Account konnte sich anmelden"

    # Und auch mit einer noch bestehenden Sitzung darf nichts mehr gehen.
    dashboard = await client.get("/", follow_redirects=False)
    assert dashboard.status_code in (303, 401, 403)


@pytest.mark.asyncio
async def test_admin_kann_sich_nicht_selbst_sperren(client: AsyncClient, session_maker, admin_welt):
    await login(client, admin_welt["admin_email"], admin_welt["admin_passwort"])
    antwort = await client.post(
        f"/admin/benutzer/{admin_welt['admin_id']}/aktiv-umschalten",
        data={"csrf_token": await _csrf_token(client)},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    assert "fehler=" in antwort.headers["location"]
    assert (await _benutzer(session_maker, admin_welt["admin_id"])).aktiv is True


# ---------------------------------------------------------------------------
# Passwort zurücksetzen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_setzt_passwort_zurueck(client: AsyncClient, session_maker, admin_welt):
    vorher = (await _benutzer(session_maker, admin_welt["teilnehmer_id"])).password_hash

    await login(client, admin_welt["admin_email"], admin_welt["admin_passwort"])
    antwort = await client.post(
        f"/admin/benutzer/{admin_welt['teilnehmer_id']}/passwort-zuruecksetzen",
        data={"csrf_token": await _csrf_token(client), "neues_passwort": "ganz-neues-passwort"},
        follow_redirects=False,
    )
    assert antwort.status_code == 303

    nachher = await _benutzer(session_maker, admin_welt["teilnehmer_id"])
    assert nachher.password_hash != vorher
    assert verify_password("ganz-neues-passwort", nachher.password_hash)
    # Das alte Passwort darf nicht weiter gelten.
    assert not verify_password(admin_welt["teilnehmer_passwort"], nachher.password_hash)


@pytest.mark.asyncio
async def test_zu_kurzer_reset_aendert_nichts(client: AsyncClient, session_maker, admin_welt):
    vorher = (await _benutzer(session_maker, admin_welt["teilnehmer_id"])).password_hash

    await login(client, admin_welt["admin_email"], admin_welt["admin_passwort"])
    antwort = await client.post(
        f"/admin/benutzer/{admin_welt['teilnehmer_id']}/passwort-zuruecksetzen",
        data={"csrf_token": await _csrf_token(client), "neues_passwort": "kurz"},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    assert "fehler=" in antwort.headers["location"]
    assert (await _benutzer(session_maker, admin_welt["teilnehmer_id"])).password_hash == vorher


@pytest.mark.asyncio
async def test_teilnehmer_kann_fremdes_passwort_nicht_zuruecksetzen(
    client: AsyncClient, session_maker, admin_welt
):
    """Kontoübernahme über den Reset-Endpunkt - der direkteste Weg an fremde
    Gesundheitsdaten, wenn die Rollenprüfung fehlt."""
    vorher = (await _benutzer(session_maker, admin_welt["admin_id"])).password_hash

    await login(client, admin_welt["teilnehmer_email"], admin_welt["teilnehmer_passwort"])
    antwort = await client.post(
        f"/admin/benutzer/{admin_welt['admin_id']}/passwort-zuruecksetzen",
        data={"csrf_token": await _csrf_token(client), "neues_passwort": "uebernommen123"},
    )
    assert antwort.status_code == 403
    assert (await _benutzer(session_maker, admin_welt["admin_id"])).password_hash == vorher


@pytest.mark.asyncio
async def test_reset_fuer_unbekannten_benutzer_ist_404(client: AsyncClient, admin_welt):
    await login(client, admin_welt["admin_email"], admin_welt["admin_passwort"])
    antwort = await client.post(
        "/admin/benutzer/999999/passwort-zuruecksetzen",
        data={"csrf_token": await _csrf_token(client), "neues_passwort": "ganz-neues-passwort"},
    )
    assert antwort.status_code == 404
