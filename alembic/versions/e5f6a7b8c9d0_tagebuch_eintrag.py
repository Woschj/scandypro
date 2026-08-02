"""wohlbefindeneintrag (Stimmungs-/Energie-Skala) durch tagebucheintrag (5-Minuten-Tagebuch) ersetzt

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-02 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.core.crypto

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bewusst kein Migrations-Pfad fuer Bestandsdaten: die Stimmungs-/
    # Energie-Skala wird durch ein komplett anderes Datenmodell (Freitext
    # statt Zahlenwerte) ersetzt, es gibt keine sinnvolle 1:1-Uebersetzung.
    # Hard-Delete ist fuer diese Datenkategorie ohnehin vorgeschrieben
    # (siehe CLAUDE.md Abschnitt 3/10).
    op.drop_index("ix_wohlbefindeneintrag_teilnehmer_id", table_name="wohlbefindeneintrag")
    op.drop_index("ix_wohlbefindeneintrag_datum", table_name="wohlbefindeneintrag")
    op.drop_table("wohlbefindeneintrag")

    op.create_table(
        "tagebucheintrag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("teilnehmer_id", sa.Integer(), nullable=False),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("dankbarkeit_1", app.core.crypto.VerschluesselterText(), nullable=True),
        sa.Column("dankbarkeit_2", app.core.crypto.VerschluesselterText(), nullable=True),
        sa.Column("dankbarkeit_3", app.core.crypto.VerschluesselterText(), nullable=True),
        sa.Column("morgen_impuls_frage", sa.String(), nullable=True),
        sa.Column("morgen_impuls_antwort", app.core.crypto.VerschluesselterText(), nullable=True),
        sa.Column("morgen_ausgefuellt_am", sa.DateTime(), nullable=True),
        sa.Column("highlight_1", app.core.crypto.VerschluesselterText(), nullable=True),
        sa.Column("highlight_2", app.core.crypto.VerschluesselterText(), nullable=True),
        sa.Column("highlight_3", app.core.crypto.VerschluesselterText(), nullable=True),
        sa.Column("abend_impuls_frage", sa.String(), nullable=True),
        sa.Column("abend_impuls_antwort", app.core.crypto.VerschluesselterText(), nullable=True),
        sa.Column("abend_ausgefuellt_am", sa.DateTime(), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["teilnehmer_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("teilnehmer_id", "datum"),
    )
    op.create_index(op.f("ix_tagebucheintrag_teilnehmer_id"), "tagebucheintrag", ["teilnehmer_id"])
    op.create_index(op.f("ix_tagebucheintrag_datum"), "tagebucheintrag", ["datum"])


def downgrade() -> None:
    op.drop_index(op.f("ix_tagebucheintrag_datum"), table_name="tagebucheintrag")
    op.drop_index(op.f("ix_tagebucheintrag_teilnehmer_id"), table_name="tagebucheintrag")
    op.drop_table("tagebucheintrag")

    op.create_table(
        "wohlbefindeneintrag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("teilnehmer_id", sa.Integer(), nullable=False),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("stimmung", sa.Float(), nullable=False),
        sa.Column("belastbarkeit", sa.Float(), nullable=False),
        sa.Column("kommentar", app.core.crypto.VerschluesselterText(), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(), nullable=False),
        sa.Column("aktualisiert_am", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["teilnehmer_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("teilnehmer_id", "datum"),
    )
    op.create_index(op.f("ix_wohlbefindeneintrag_datum"), "wohlbefindeneintrag", ["datum"])
    op.create_index(op.f("ix_wohlbefindeneintrag_teilnehmer_id"), "wohlbefindeneintrag", ["teilnehmer_id"])
