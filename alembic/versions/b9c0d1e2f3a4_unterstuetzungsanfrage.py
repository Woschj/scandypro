"""unterstuetzungsanfrage: freiwillige Unterstuetzungs-Anfrage aus Mein Tag

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-08-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "unterstuetzungsanfrage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("teilnehmer_id", sa.Integer(), nullable=False),
        sa.Column("empfaenger_id", sa.Integer(), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(), nullable=False),
        sa.Column("gesehen_am", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["teilnehmer_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["empfaenger_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_unterstuetzungsanfrage_teilnehmer_id"), "unterstuetzungsanfrage", ["teilnehmer_id"])
    op.create_index(op.f("ix_unterstuetzungsanfrage_empfaenger_id"), "unterstuetzungsanfrage", ["empfaenger_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_unterstuetzungsanfrage_empfaenger_id"), table_name="unterstuetzungsanfrage")
    op.drop_index(op.f("ix_unterstuetzungsanfrage_teilnehmer_id"), table_name="unterstuetzungsanfrage")
    op.drop_table("unterstuetzungsanfrage")
