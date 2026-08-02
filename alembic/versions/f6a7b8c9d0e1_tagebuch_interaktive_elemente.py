"""tagebucheintrag: interaktive Elemente (Atemuebung, Energie-Batterie, Zeichnung, Checkliste)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-02 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tagebucheintrag", sa.Column("energie_level", sa.Integer(), nullable=True))
    op.add_column("tagebucheintrag", sa.Column("atemuebung_erledigt_am", sa.DateTime(), nullable=True))
    op.add_column("tagebucheintrag", sa.Column("zeichnung_pfad", sa.String(), nullable=True))
    op.add_column(
        "tagebucheintrag",
        sa.Column("check_pause_gemacht", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "tagebucheintrag",
        sa.Column("check_jemandem_geholfen", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "tagebucheintrag",
        sa.Column("check_kleines_erfolgserlebnis", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("tagebucheintrag", "check_kleines_erfolgserlebnis")
    op.drop_column("tagebucheintrag", "check_jemandem_geholfen")
    op.drop_column("tagebucheintrag", "check_pause_gemacht")
    op.drop_column("tagebucheintrag", "zeichnung_pfad")
    op.drop_column("tagebucheintrag", "atemuebung_erledigt_am")
    op.drop_column("tagebucheintrag", "energie_level")
