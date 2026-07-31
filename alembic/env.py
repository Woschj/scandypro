"""Alembic-Migrationen für ScandyPro.

target_metadata kommt aus SQLModel (alle Models über app.models importiert -
siehe dortiges __init__.py, das jede Tabelle exportiert und damit in
SQLModel.metadata registriert). Nutzt eine synchrone Engine (psycopg2),
auch wenn die App selbst async/asyncpg läuft - Alembic braucht hier keinen
Event-Loop.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

import app.models  # noqa: F401  (registriert alle Tabellen in SQLModel.metadata)
from app.core.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _sync_database_url() -> str:
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


config.set_main_option("sqlalchemy.url", _sync_database_url())


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
