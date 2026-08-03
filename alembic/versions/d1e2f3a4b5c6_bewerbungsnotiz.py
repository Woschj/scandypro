"""bewerbungsnotiz: Notizverlauf statt einzelnem notizen-Feld

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-08-03 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.core.crypto

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c0d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bewerbungsnotiz",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bewerbung_id", sa.Integer(), nullable=False),
        sa.Column("text", app.core.crypto.VerschluesselterText(), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["bewerbung_id"], ["bewerbung.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bewerbungsnotiz_bewerbung_id"), "bewerbungsnotiz", ["bewerbung_id"])

    # Bestehende Einzel-Notizen als ersten Verlaufs-Eintrag uebernehmen,
    # bevor die Spalte verschwindet - der verschluesselte Rohwert kann 1:1
    # kopiert werden, da beide Spalten denselben VerschluesselterText-Typ
    # nutzen (gleicher Schluessel/gleiche Transformation).
    op.execute(
        "INSERT INTO bewerbungsnotiz (bewerbung_id, text, erstellt_am) "
        "SELECT id, notizen, erstellt_am FROM bewerbung WHERE notizen IS NOT NULL"
    )

    op.drop_column("bewerbung", "notizen")


def downgrade() -> None:
    op.add_column("bewerbung", sa.Column("notizen", app.core.crypto.VerschluesselterText(), nullable=True))
    op.execute(
        "UPDATE bewerbung SET notizen = n.text FROM ("
        "  SELECT DISTINCT ON (bewerbung_id) bewerbung_id, text FROM bewerbungsnotiz ORDER BY bewerbung_id, erstellt_am"
        ") n WHERE bewerbung.id = n.bewerbung_id"
    )
    op.drop_index(op.f("ix_bewerbungsnotiz_bewerbung_id"), table_name="bewerbungsnotiz")
    op.drop_table("bewerbungsnotiz")
