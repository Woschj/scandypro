"""auditaktion/auditzieltyp: Wochenbericht-Zugriff und Datenexport ergaenzen

Revision ID: d5e6f7a8b9c1
Revises: c4d5e6f7a8b9
Create Date: 2026-08-12 09:00:00.000000

Siehe tasks/codebase-audit/README.md, CA-002: CLAUDE.md Abschnitt 4 verlangt
die Protokollierung *jedes* Zugriffs auf sensible Daten. Bisher waren nur
Wohlbefinden- und Bewerbungs-Fremdansichten abgedeckt.

Native Postgres-Enums lassen sich nur per ALTER TYPE erweitern (analog
c0d1e2f3a4b5). ADD VALUE ist nicht transaktional rueckbaubar - ein
downgrade kann die Werte daher nicht entfernen (siehe unten).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d5e6f7a8b9c1"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEUE_AKTIONEN = ("wochenbericht_gelesen", "daten_exportiert")
_NEUE_ZIELTYPEN = ("wochenbericht", "eigene_daten")


def upgrade() -> None:
    # ADD VALUE laeuft in aelteren Postgres-Versionen nicht in einem
    # Transaktionsblock - commit() beendet die von Alembic geoeffnete
    # Transaktion, danach laeuft jedes Statement autocommit.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("COMMIT")
        for wert in _NEUE_AKTIONEN:
            op.execute(f"ALTER TYPE auditaktion ADD VALUE IF NOT EXISTS '{wert}'")
        for wert in _NEUE_ZIELTYPEN:
            op.execute(f"ALTER TYPE auditzieltyp ADD VALUE IF NOT EXISTS '{wert}'")


def downgrade() -> None:
    # Postgres kann einzelne Enum-Werte nicht entfernen; ein sauberes
    # Downgrade muesste den Typ neu aufbauen und alle Spalten umhaengen.
    # Da ueberzaehlige Enum-Werte niemanden stoeren (sie werden nach dem
    # Downgrade schlicht nicht mehr geschrieben), bleibt das bewusst ein
    # No-Op statt einer riskanten Typ-Neuanlage auf Produktivdaten.
    pass
