"""KartenBewegung - Protokoll von Karten-Vorwaertsbewegungen fuer das Wochen-Fortschritts-Signal

Revision ID: d4e5f6a7b8c9
Revises: c8d9e0f1a2b3
Create Date: 2026-08-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kartenbewegung",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("karte_id", sa.Integer(), nullable=False),
        sa.Column("bewegt_von_id", sa.Integer(), nullable=False),
        sa.Column("bewegt_am", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["karte_id"], ["karte.id"]),
        sa.ForeignKeyConstraint(["bewegt_von_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_kartenbewegung_karte_id"), "kartenbewegung", ["karte_id"])
    op.create_index(op.f("ix_kartenbewegung_bewegt_von_id"), "kartenbewegung", ["bewegt_von_id"])
    # Bewusst kein Backfill: Bestandskarten, die vor dieser Migration schon
    # in der Erledigt-Spalte lagen, wurden bereits ueber Karte.abgeschlossen_am
    # als "Schritt" gezaehlt (siehe c8d9e0f1a2b3) - ein rueckwirkender
    # Bewegungs-Eintrag wuerde denselben historischen Abschluss doppelt als
    # Schritt zaehlen, sobald woechentliche_schritte() umgestellt ist.


def downgrade() -> None:
    op.drop_index(op.f("ix_kartenbewegung_bewegt_von_id"), table_name="kartenbewegung")
    op.drop_index(op.f("ix_kartenbewegung_karte_id"), table_name="kartenbewegung")
    op.drop_table("kartenbewegung")
