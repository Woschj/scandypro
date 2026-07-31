import asyncio
from collections.abc import AsyncGenerator

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _alembic_upgrade_head() -> None:
    """Synchron (Alembic/psycopg2), siehe alembic/env.py - läuft daher in
    init_db() über run_in_executor, um den Event-Loop nicht zu blockieren."""
    command.upgrade(Config("alembic.ini"), "head")


async def init_db() -> None:
    """Bringt das Schema per Alembic auf den neuesten Stand (ersetzt das
    frühere `create_all` aus der Prototyp-Phase, siehe alembic/versions/)."""
    await asyncio.get_event_loop().run_in_executor(None, _alembic_upgrade_head)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
