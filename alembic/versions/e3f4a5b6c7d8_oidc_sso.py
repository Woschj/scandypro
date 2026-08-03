"""oidc_sso: Single-Sign-On-Vorbereitung (auth_source, external_id, Rolle/Passwort optional)

Revision ID: e3f4a5b6c7d8
Revises: d1e2f3a4b5c6
Create Date: 2026-08-03 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("auth_source", sa.String(), nullable=False, server_default="local"))
    op.add_column("user", sa.Column("external_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_user_external_id"), "user", ["external_id"], unique=True)
    op.alter_column("user", "password_hash", existing_type=sa.String(), nullable=True)
    op.alter_column("user", "role", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.alter_column("user", "role", existing_type=sa.String(), nullable=False)
    op.alter_column("user", "password_hash", existing_type=sa.String(), nullable=False)
    op.drop_index(op.f("ix_user_external_id"), table_name="user")
    op.drop_column("user", "external_id")
    op.drop_column("user", "auth_source")
