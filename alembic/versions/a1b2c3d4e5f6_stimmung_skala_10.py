"""stimmung/belastbarkeit auf 1-10 Skala umstellen

Revision ID: a1b2c3d4e5f6
Revises: ff957f57f077
Create Date: 2026-07-31 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "ff957f57f077"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Bestehende Werte lagen auf einer 1.0-5.0-Skala (0.5-Schritte). Die neue
# Emoji-Kachel-Skala hat 10 diskrete Stufen (siehe app/core/skala.py) - die
# Rescale-Formel bildet 1->1 und 5->10 linear ab, gerundet auf ganze Zahlen.
_RESCALE_HOCH = "GREATEST(1, LEAST(10, ROUND(1 + ({spalte} - 1) / 4.0 * 9)))::integer"
_RESCALE_RUNTER = "GREATEST(1.0, LEAST(5.0, 1 + ({spalte} - 1) / 9.0 * 4))::float"


def upgrade() -> None:
    for spalte in ("stimmung", "belastbarkeit"):
        op.execute(
            f"ALTER TABLE wohlbefindeneintrag "
            f"ALTER COLUMN {spalte} TYPE INTEGER USING {_RESCALE_HOCH.format(spalte=spalte)}"
        )


def downgrade() -> None:
    for spalte in ("stimmung", "belastbarkeit"):
        op.execute(
            f"ALTER TABLE wohlbefindeneintrag "
            f"ALTER COLUMN {spalte} TYPE FLOAT USING {_RESCALE_RUNTER.format(spalte=spalte)}"
        )
