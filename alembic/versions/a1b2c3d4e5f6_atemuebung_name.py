"""tagebucheintrag: atemuebung_name (rotierender Atemuebungs-Pool)

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-08-03 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tagebucheintrag", sa.Column("atemuebung_name", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("tagebucheintrag", "atemuebung_name")
