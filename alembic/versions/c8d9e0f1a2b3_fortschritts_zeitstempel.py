"""Karte.abgeschlossen_am + Unteraufgabe.erledigt_am - Basis für privates Wochen-Fortschritts-Signal

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-08-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("karte", sa.Column("abgeschlossen_am", sa.DateTime(), nullable=True))
    op.add_column("unteraufgabe", sa.Column("erledigt_am", sa.DateTime(), nullable=True))
    # Backfill: Bestandskarten, die schon in der Erledigt-Spalte liegen, und
    # bereits erledigte Unteraufgaben bekommen den Migrationszeitpunkt als
    # Näherung - so tauchen sie nicht fälschlich als "diese Woche erledigt"
    # auf, sind aber ab jetzt korrekt für künftige Zeiträume berücksichtigt.
    op.execute(
        """
        UPDATE karte SET abgeschlossen_am = karte.erstellt_am
        FROM spalte
        WHERE karte.spalte_id = spalte.id AND spalte.ist_system_erledigt = true
        """
    )
    op.execute("UPDATE unteraufgabe SET erledigt_am = erstellt_am WHERE erledigt = true")


def downgrade() -> None:
    op.drop_column("unteraufgabe", "erledigt_am")
    op.drop_column("karte", "abgeschlossen_am")
