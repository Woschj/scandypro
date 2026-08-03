"""bewerbung: naechster_termin_uhrzeit + naechster_termin_ort (VB-009)

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-08-03 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bewerbung", sa.Column("naechster_termin_uhrzeit", sa.String(), nullable=True))
    op.add_column("bewerbung", sa.Column("naechster_termin_ort", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("bewerbung", "naechster_termin_ort")
    op.drop_column("bewerbung", "naechster_termin_uhrzeit")
