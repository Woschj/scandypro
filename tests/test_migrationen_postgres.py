"""Echter Migrationslauf gegen PostgreSQL (PR-002).

`tests/test_migrationen.py` prüft die Kette *statisch* - doppelte
Revision-IDs, mehrere Heads, Lücken. Das fängt die Fehlerklasse ab, die
schon einmal einen Deploy blockiert hat, führt die Migrationen aber nie
aus. Postgres-spezifisches SQL (`ALTER TYPE ... ADD VALUE`,
`ALTER COLUMN ... USING`) fällt dabei durch.

Diese Tests schließen die Lücke: sie legen eine **Wegwerf-Datenbank** an,
fahren `alembic upgrade head` dagegen, vergleichen das Ergebnis mit den
SQLModel-Modellen und räumen wieder auf.

Ausführen (Postgres läuft z.B. schon über docker compose):

    docker compose up -d db
    TEST_POSTGRES_URL=postgresql+psycopg2://scandypro:PASSWORT@localhost:5432/postgres \\
        python -m pytest tests/test_migrationen_postgres.py -v

Ohne `TEST_POSTGRES_URL` werden die Tests übersprungen - der normale
Testlauf soll keine laufende Datenbank voraussetzen.

Sicherheit: Es wird immer eine eigene Datenbank mit zufälligem Namen
angelegt und am Ende gelöscht. Die in `TEST_POSTGRES_URL` genannte
Datenbank dient nur als Einstiegspunkt zum Server und wird nie verändert.
"""
import os
import uuid

import pytest

pytest.importorskip("psycopg2", reason="psycopg2 wird für den Postgres-Migrationstest gebraucht")

import sqlalchemy as sa  # noqa: E402
from alembic import command  # noqa: E402
from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

import app.models  # noqa: E402,F401  (registriert alle Tabellen)

SERVER_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not SERVER_URL,
    reason="TEST_POSTGRES_URL nicht gesetzt - siehe Modul-Docstring zum Ausführen",
)

PROJEKT_WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def wegwerf_datenbank():
    """Legt eine frische, leere Datenbank an und löscht sie danach wieder."""
    name = f"scandypro_migrationstest_{uuid.uuid4().hex[:12]}"

    verwaltung = sa.create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")
    ziel_url = sa.engine.make_url(SERVER_URL).set(database=name)

    # Doppelte Absicherung: der generierte Name darf niemals die Datenbank
    # aus der Einstiegs-URL sein.
    assert name != sa.engine.make_url(SERVER_URL).database
    assert "migrationstest" in name

    with verwaltung.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    try:
        yield ziel_url
    finally:
        with verwaltung.connect() as conn:
            conn.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": name},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        verwaltung.dispose()


def _alembic_konfig(ziel_url) -> Config:
    konfig = Config(os.path.join(PROJEKT_WURZEL, "alembic.ini"))
    konfig.set_main_option("script_location", os.path.join(PROJEKT_WURZEL, "alembic"))
    # Muss gesetzt sein, BEVOR env.py läuft - dort hat eine vorhandene URL
    # Vorrang vor settings.database_url (siehe alembic/env.py).
    konfig.set_main_option("sqlalchemy.url", str(ziel_url))
    return konfig


def test_upgrade_head_laeuft_durch(wegwerf_datenbank):
    """Der Lauf, den es bisher nur beim echten Deploy gab."""
    command.upgrade(_alembic_konfig(wegwerf_datenbank), "head")

    motor = sa.create_engine(wegwerf_datenbank)
    with motor.connect() as conn:
        tabellen = set(sa.inspect(conn).get_table_names())
    motor.dispose()

    # Stichproben quer durch die Domänen - wenn die Kette durchläuft, aber
    # Tabellen fehlen, ist auch etwas faul.
    for erwartet in ("user", "karte", "spalte", "tagebucheintrag", "bewerbung", "auditlogeintrag"):
        assert erwartet in tabellen, f"Tabelle {erwartet} fehlt nach upgrade head"
    assert "alembic_version" in tabellen


def test_kein_drift_zwischen_migrationen_und_modellen(wegwerf_datenbank):
    """Nach `upgrade head` muss das Schema den SQLModel-Modellen entsprechen.

    Schlägt an, wenn jemand ein Feld am Modell ändert und die Migration
    vergisst - der Fehler fällt sonst erst auf, wenn eine Query gegen eine
    Spalte läuft, die es in der Datenbank nicht gibt.
    """
    command.upgrade(_alembic_konfig(wegwerf_datenbank), "head")

    motor = sa.create_engine(wegwerf_datenbank)
    with motor.connect() as conn:
        kontext = MigrationContext.configure(conn)
        unterschiede = compare_metadata(kontext, SQLModel.metadata)
    motor.dispose()

    # alembic_version gehört Alembic selbst und taucht nicht in den Modellen
    # auf - das ist kein Drift.
    relevant = [
        d for d in unterschiede
        if not (isinstance(d, tuple) and len(d) > 1 and getattr(d[1], "name", None) == "alembic_version")
    ]
    assert not relevant, "Schema weicht von den Modellen ab:\n" + "\n".join(repr(d) for d in relevant)


def test_downgrade_und_erneutes_upgrade(wegwerf_datenbank):
    """Rundlauf head -> base -> head.

    Deckt ab, dass die downgrade()-Zweige nicht bloß Dekoration sind - sie
    sind der Rückweg, wenn ein Deploy schiefgeht.
    """
    konfig = _alembic_konfig(wegwerf_datenbank)
    command.upgrade(konfig, "head")
    command.downgrade(konfig, "base")

    motor = sa.create_engine(wegwerf_datenbank)
    with motor.connect() as conn:
        nach_downgrade = set(sa.inspect(conn).get_table_names())
    # Nach base darf außer Alembics eigener Tabelle nichts übrig sein.
    assert nach_downgrade <= {"alembic_version"}, f"Reste nach downgrade base: {nach_downgrade}"

    command.upgrade(konfig, "head")
    with motor.connect() as conn:
        nach_upgrade = set(sa.inspect(conn).get_table_names())
    motor.dispose()
    assert "user" in nach_upgrade and "tagebucheintrag" in nach_upgrade


def test_schrittweise_durch_jede_revision(wegwerf_datenbank):
    """Jede Migration einzeln anwenden statt in einem Rutsch.

    `upgrade head` führt zwar alle aus, verdeckt aber, welche eine
    Transaktion offen lässt oder auf Zustand aus einer späteren Revision
    angewiesen ist. Der Fehler aus 0.1.41 (`ALTER TYPE ... ADD VALUE` mit
    explizitem COMMIT) ist genau von dieser Sorte.
    """
    from alembic.script import ScriptDirectory

    konfig = _alembic_konfig(wegwerf_datenbank)
    skripte = ScriptDirectory.from_config(konfig)
    revisionen = [s.revision for s in reversed(list(skripte.walk_revisions()))]
    assert len(revisionen) > 5, "Unerwartet wenige Revisionen gefunden"

    for revision in revisionen:
        command.upgrade(konfig, revision)

    motor = sa.create_engine(wegwerf_datenbank)
    with motor.connect() as conn:
        stand = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    motor.dispose()
    assert stand == revisionen[-1]
