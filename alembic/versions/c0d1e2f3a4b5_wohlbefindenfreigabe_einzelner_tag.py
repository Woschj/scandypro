"""wohlbefindenfreigabe: einzelnen Tag statt nur alles/befristet freigeben

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-08-03 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c0d1e2f3a4b5"
down_revision: Union[str, None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Natives Postgres-Enum - neue Werte muessen per ALTER TYPE ergaenzt
    # werden, das SQLModel/SQLAlchemy-Enum auf Python-Seite reicht nicht.
    op.execute("ALTER TYPE wohlbefindenfreigabeumfang ADD VALUE IF NOT EXISTS 'einzeln'")
    op.add_column("wohlbefindenfreigabe", sa.Column("tagebuch_eintrag_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_wohlbefindenfreigabe_tagebuch_eintrag_id"), "wohlbefindenfreigabe", ["tagebuch_eintrag_id"]
    )
    op.create_foreign_key(
        "fk_wohlbefindenfreigabe_tagebuch_eintrag_id_tagebucheintrag",
        "wohlbefindenfreigabe",
        "tagebucheintrag",
        ["tagebuch_eintrag_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_wohlbefindenfreigabe_tagebuch_eintrag_id_tagebucheintrag", "wohlbefindenfreigabe", type_="foreignkey"
    )
    op.drop_index(op.f("ix_wohlbefindenfreigabe_tagebuch_eintrag_id"), table_name="wohlbefindenfreigabe")
    op.drop_column("wohlbefindenfreigabe", "tagebuch_eintrag_id")
