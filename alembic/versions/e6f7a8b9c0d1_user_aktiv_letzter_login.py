"""user: aktiv + letzter_login (VB-012)

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-08-03 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("user", sa.Column("letzter_login", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("user", "letzter_login")
    op.drop_column("user", "aktiv")
