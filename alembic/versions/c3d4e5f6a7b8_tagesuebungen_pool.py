"""tagebucheintrag: erweiterter Uebungspool (Koerperscan, Erdung, Wort des
Tages, Staerken-Karte, Mandala, Ruhe-Ort, Gedanken-Waage, Sorgen loslassen,
Dankbarkeitsfoto, Mini-Ziel) - siehe app/core/tagesuebungen.py,
tasks/ganzheitliche-verbesserungen/VB-006.md

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.core.crypto

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tagebucheintrag", sa.Column("morgen_uebung_typ", sa.String(), nullable=True))
    op.add_column("tagebucheintrag", sa.Column("koerperscan_erledigt_am", sa.DateTime(), nullable=True))
    op.add_column("tagebucheintrag", sa.Column("grounding_erledigt_am", sa.DateTime(), nullable=True))
    op.add_column("tagebucheintrag", sa.Column("wort_des_tages", app.core.crypto.VerschluesselterText(), nullable=True))
    op.add_column("tagebucheintrag", sa.Column("staerken_karte_frage", sa.String(), nullable=True))
    op.add_column(
        "tagebucheintrag", sa.Column("staerken_karte_antwort", app.core.crypto.VerschluesselterText(), nullable=True)
    )
    op.add_column("tagebucheintrag", sa.Column("staerken_karte_erledigt_am", sa.DateTime(), nullable=True))

    op.add_column("tagebucheintrag", sa.Column("abend_uebung_typ", sa.String(), nullable=True))
    op.add_column("tagebucheintrag", sa.Column("mandala_erledigt_am", sa.DateTime(), nullable=True))
    op.add_column(
        "tagebucheintrag", sa.Column("ruhe_ort_sehen", app.core.crypto.VerschluesselterText(), nullable=True)
    )
    op.add_column(
        "tagebucheintrag", sa.Column("ruhe_ort_hoeren", app.core.crypto.VerschluesselterText(), nullable=True)
    )
    op.add_column(
        "tagebucheintrag", sa.Column("ruhe_ort_spueren", app.core.crypto.VerschluesselterText(), nullable=True)
    )
    op.add_column(
        "tagebucheintrag", sa.Column("gedanke_belastend", app.core.crypto.VerschluesselterText(), nullable=True)
    )
    op.add_column(
        "tagebucheintrag", sa.Column("gedanke_ausgewogen", app.core.crypto.VerschluesselterText(), nullable=True)
    )
    op.add_column("tagebucheintrag", sa.Column("sorgen_los_erledigt_am", sa.DateTime(), nullable=True))
    op.add_column("tagebucheintrag", sa.Column("dankbarkeitsfoto_pfad", sa.String(), nullable=True))
    op.add_column(
        "tagebucheintrag", sa.Column("mini_ziel_text", app.core.crypto.VerschluesselterText(), nullable=True)
    )
    op.add_column(
        "tagebucheintrag",
        sa.Column("mini_ziel_geschafft", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("tagebucheintrag", "mini_ziel_geschafft")
    op.drop_column("tagebucheintrag", "mini_ziel_text")
    op.drop_column("tagebucheintrag", "dankbarkeitsfoto_pfad")
    op.drop_column("tagebucheintrag", "sorgen_los_erledigt_am")
    op.drop_column("tagebucheintrag", "gedanke_ausgewogen")
    op.drop_column("tagebucheintrag", "gedanke_belastend")
    op.drop_column("tagebucheintrag", "ruhe_ort_spueren")
    op.drop_column("tagebucheintrag", "ruhe_ort_hoeren")
    op.drop_column("tagebucheintrag", "ruhe_ort_sehen")
    op.drop_column("tagebucheintrag", "mandala_erledigt_am")
    op.drop_column("tagebucheintrag", "abend_uebung_typ")

    op.drop_column("tagebucheintrag", "staerken_karte_erledigt_am")
    op.drop_column("tagebucheintrag", "staerken_karte_antwort")
    op.drop_column("tagebucheintrag", "staerken_karte_frage")
    op.drop_column("tagebucheintrag", "wort_des_tages")
    op.drop_column("tagebucheintrag", "grounding_erledigt_am")
    op.drop_column("tagebucheintrag", "koerperscan_erledigt_am")
    op.drop_column("tagebucheintrag", "morgen_uebung_typ")
