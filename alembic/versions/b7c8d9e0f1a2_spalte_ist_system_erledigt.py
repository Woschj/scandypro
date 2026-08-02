"""Spalte.ist_system_erledigt - fixierte Erledigt-Spalte je Board

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-08-02 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "spalte",
        sa.Column("ist_system_erledigt", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Backfill: auf Bestandsdaten war "Erledigt" bereits per Konvention die
    # letzte Standard-Spalte (siehe app/routers/kanban.py:STANDARD_SPALTEN) -
    # jetzt wird das strukturell fixiert statt nur benannt.
    op.execute("UPDATE spalte SET ist_system_erledigt = true WHERE name = 'Erledigt'")


def downgrade() -> None:
    op.drop_column("spalte", "ist_system_erledigt")
