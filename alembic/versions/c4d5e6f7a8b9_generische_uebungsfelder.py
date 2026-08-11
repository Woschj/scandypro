"""tagebucheintrag: generische Uebungs-Ergebnisfelder (morgen_uebung_*/abend_uebung_*)

Revision ID: c4d5e6f7a8b9
Revises: f1a2b3c4d5e6
Create Date: 2026-08-04 12:00:00.000000

Additiv: acht neue nullable Spalten, kein Datenverlust. Die aelteren,
typ-spezifischen Felder (koerperscan_erledigt_am, wort_des_tages, ...)
bleiben unveraendert bestehen und weiter in Benutzung - nur die ab VB-019
ergaenzten Uebungstypen nutzen das generische Schema (siehe
app/models/wohlbefinden.py).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.core.crypto

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SPALTEN = [
    ("morgen_uebung_erledigt_am", sa.DateTime()),
    ("morgen_uebung_frage", sa.String()),
    ("morgen_uebung_ergebnis", app.core.crypto.VerschluesselterText()),
    ("morgen_uebung_datei_pfad", sa.String()),
    ("abend_uebung_erledigt_am", sa.DateTime()),
    ("abend_uebung_frage", sa.String()),
    ("abend_uebung_ergebnis", app.core.crypto.VerschluesselterText()),
    ("abend_uebung_datei_pfad", sa.String()),
]


def upgrade() -> None:
    for name, typ in _SPALTEN:
        op.add_column("tagebucheintrag", sa.Column(name, typ, nullable=True))


def downgrade() -> None:
    for name, _typ in reversed(_SPALTEN):
        op.drop_column("tagebucheintrag", name)
