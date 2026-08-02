"""
Gemeinsame Test-Fixtures: frische SQLite-DB pro Test (aiosqlite,
PRAGMA foreign_keys=ON - SQLite prüft Fremdschlüssel standardmäßig NICHT,
das könnte reale Postgres-Bugs verdecken), plus ein httpx.AsyncClient gegen
die echte FastAPI-App (app.core.database.get_session wird per
dependency_overrides auf die Test-Engine umgebogen).

Struktur an das Schwestermodul Scandy-Lite angeglichen (dort:
tests/conftest.py) - Domänen-Fixtures (hier: Abteilung + Teilnehmer:in
statt Department + Mitarbeiter-Barcode) sind natürlich ScandyPro-eigen.
"""
import os
import tempfile

# WICHTIG: Muss VOR jedem "app.*"-Import passieren - app/core/config.py
# instanziiert Settings() beim Modul-Import (benötigt database_url/secret_key/
# field_encryption_key ohne Default), app/core/crypto.py baut daraus beim
# Import direkt ein Fernet-Objekt (validiert das Schlüsselformat sofort).
# Die eigentliche Test-DB ist eine separate SQLite-Engine (siehe engine()
# unten) - settings.database_url wird nie tatsächlich verbunden, da
# init_db()/Alembic in Tests nie läuft (httpx.ASGITransport löst keine
# Lifespan-Events aus).
from cryptography.fernet import Fernet

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-nur-fuer-tests")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", Fernet.generate_key().decode())

import app.models  # noqa: E402,F401  (registriert alle Tabellen in SQLModel.metadata)
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402
from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: E402

from app.core import database as db_module  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.organisation import Abteilung  # noqa: E402
from app.models.user import RoleEnum, User  # noqa: E402

TEILNEHMER_EMAIL = "teilnehmer@test.local"
TEILNEHMER_PASSWORT = "testpass123"


@pytest_asyncio.fixture
async def engine():
    # Datei-basierte SQLite-DB statt ":memory:" - jede Session bekommt so eine
    # eigene, echte Connection mit korrekter Transaktions-Isolation (siehe
    # identische Begründung im Schwestermodul Scandy-Lite, tests/conftest.py).
    fd, db_path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    @event.listens_for(test_engine.sync_engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield test_engine
    await test_engine.dispose()
    os.remove(db_path)


@pytest_asyncio.fixture
async def session_maker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def seed_data(session_maker):
    """Eine Abteilung + ein Teilnehmer-Login - deckt den häufigsten
    Berechtigungsfall ab (eigene Daten lesen/schreiben)."""
    async with session_maker() as session:
        abteilung = Abteilung(name="Medien & Digital")
        session.add(abteilung)
        await session.commit()
        await session.refresh(abteilung)

        teilnehmer = User(
            name="Test Teilnehmer:in",
            email=TEILNEHMER_EMAIL,
            password_hash=hash_password(TEILNEHMER_PASSWORT),
            role=RoleEnum.teilnehmer,
            abteilung_id=abteilung.id,
        )
        session.add(teilnehmer)
        await session.commit()
        await session.refresh(teilnehmer)

        return {
            "abteilung_id": abteilung.id,
            "teilnehmer_id": teilnehmer.id,
            "teilnehmer_email": TEILNEHMER_EMAIL,
            "teilnehmer_passwort": TEILNEHMER_PASSWORT,
        }


@pytest_asyncio.fixture
async def client(session_maker):
    async def _get_session_override():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[db_module.get_session] = _get_session_override

    # app.main.http_exception_handler öffnet für current_user (Fehlerseiten-
    # Kontext) bewusst eine eigene Session statt der Request-Dependency
    # (siehe dortigen Docstring) - importiert async_session_factory dabei
    # per `from ... import`, also als eigene Modul-Referenz, die
    # dependency_overrides nicht erreicht. Deshalb hier zusätzlich
    # app.main.async_session_factory direkt patchen, sonst zeigt jeder Test,
    # der eine HTTPException auslöst (401/403/404/...), fälschlich einen
    # 500er auf die (nie initialisierte) Produktions-Engine statt den
    # erwarteten Statuscode.
    import app.main as main_module

    original_factory = main_module.async_session_factory
    main_module.async_session_factory = session_maker

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    main_module.async_session_factory = original_factory


async def login(client: AsyncClient, email: str, passwort: str) -> None:
    resp = await client.post("/login", data={"email": email, "password": passwort})
    assert resp.status_code == 303, resp.text
