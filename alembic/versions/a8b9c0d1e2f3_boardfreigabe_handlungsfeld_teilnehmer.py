"""boardfreigabe: handlungsfeld_id + teilnehmer_id, gruppe_id nullbar

Erweitert Board-Freigaben um zwei weitere Ziel-Typen (ganzes Handlungsfeld,
einzelne Person) neben der bestehenden Arbeitsgruppen-Freigabe - siehe
app/models/kanban.py:BoardFreigabe, app/routers/kanban.py:freigabe_erstellen.

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-04 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("boardfreigabe", sa.Column("handlungsfeld_id", sa.Integer(), nullable=True))
    op.add_column("boardfreigabe", sa.Column("teilnehmer_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_boardfreigabe_handlungsfeld_id", "boardfreigabe", "handlungsfeld", ["handlungsfeld_id"], ["id"]
    )
    op.create_foreign_key("fk_boardfreigabe_teilnehmer_id", "boardfreigabe", "user", ["teilnehmer_id"], ["id"])
    op.create_index(
        op.f("ix_boardfreigabe_handlungsfeld_id"), "boardfreigabe", ["handlungsfeld_id"]
    )
    op.create_index(op.f("ix_boardfreigabe_teilnehmer_id"), "boardfreigabe", ["teilnehmer_id"])
    op.alter_column("boardfreigabe", "gruppe_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("boardfreigabe", "gruppe_id", existing_type=sa.Integer(), nullable=False)
    op.drop_index(op.f("ix_boardfreigabe_teilnehmer_id"), table_name="boardfreigabe")
    op.drop_index(op.f("ix_boardfreigabe_handlungsfeld_id"), table_name="boardfreigabe")
    op.drop_constraint("fk_boardfreigabe_teilnehmer_id", "boardfreigabe", type_="foreignkey")
    op.drop_constraint("fk_boardfreigabe_handlungsfeld_id", "boardfreigabe", type_="foreignkey")
    op.drop_column("boardfreigabe", "teilnehmer_id")
    op.drop_column("boardfreigabe", "handlungsfeld_id")
