"""konto_loeschung: Urheberschafts-Spalten nullbar, auditlogeintrag.akteur_id ohne FK

Voraussetzung für die vollständige Konto-Löschung nach Art. 17 DSGVO
(PR-005, siehe app/core/deletion.py:loesche_konto_vollstaendig).

Zwei verschiedene Behandlungen, je nach Bedeutung der Spalte:

- **Urheberschaft** (wer hat das angelegt/bewegt) wird nullbar. Der Inhalt
  bleibt bestehen und wird als "Gelöschte:r Nutzer:in" angezeigt. Auf
  Team-Boards arbeiten andere Menschen weiter; deren Karten dürfen nicht
  verschwinden, nur weil eine Person das Haus verlässt. Die Leitung kann
  solche Karten danach neu zuweisen oder von Hand löschen.
- **auditlogeintrag.akteur_id** verliert nur den Fremdschlüssel, bleibt aber
  gefüllt - genau wie ziel_teilnehmer_id, das aus demselben Grund nie einen
  FK hatte: der Eintrag soll als pseudonymisierter Nachweis überleben
  (CLAUDE.md §9), statt per Kaskade zu verschwinden.

Zugehörigkeiten (KartenZuweisung, Mitgliedschaften, Zuordnungen) brauchen
keine Schema-Änderung - sie werden beim Löschen als Zeilen entfernt, weil
eine Zuweisung an eine nicht mehr existierende Person keine Bedeutung hat.

Revision ID: e6f7a8b9c1d2
Revises: d5e6f7a8b9c1
Create Date: 2026-08-12 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e6f7a8b9c1d2"
down_revision: Union[str, None] = "d5e6f7a8b9c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (Tabelle, Spalte) der Urheberschafts-Felder
NULLBAR = [
    ("board", "ersteller_id"),
    ("karte", "ersteller_id"),
    ("kartenbewegung", "bewegt_von_id"),
    ("teilnehmergruppe", "erstellt_von"),
]


def _fk_name(inspector, tabelle: str, spalte: str) -> str | None:
    for fk in inspector.get_foreign_keys(tabelle):
        if fk.get("constrained_columns") == [spalte]:
            return fk.get("name")
    return None


def upgrade() -> None:
    for tabelle, spalte in NULLBAR:
        op.alter_column(tabelle, spalte, existing_type=sa.Integer(), nullable=True)

    # Fremdschlüssel von auditlogeintrag.akteur_id entfernen (Spalte bleibt).
    inspector = sa.inspect(op.get_bind())
    name = _fk_name(inspector, "auditlogeintrag", "akteur_id")
    if name:
        op.drop_constraint(name, "auditlogeintrag", type_="foreignkey")


def downgrade() -> None:
    # Vor dem Zurücksetzen auf NOT NULL müssten etwaige NULL-Werte behandelt
    # werden - die entstehen aber nur durch eine bereits erfolgte
    # Konto-Löschung, und dafür gibt es keine sinnvolle Umkehrung (die Person
    # ist weg). Betroffene Zeilen werden deshalb entfernt, damit der
    # Downgrade überhaupt durchläuft; ein Downgrade nach einer Löschung ist
    # ohnehin kein realistischer Pfad.
    op.execute("DELETE FROM kartenbewegung WHERE bewegt_von_id IS NULL")
    op.execute("DELETE FROM karte WHERE ersteller_id IS NULL")
    op.execute("DELETE FROM teilnehmergruppe WHERE erstellt_von IS NULL")
    op.execute("DELETE FROM board WHERE ersteller_id IS NULL")

    for tabelle, spalte in NULLBAR:
        op.alter_column(tabelle, spalte, existing_type=sa.Integer(), nullable=False)

    op.create_foreign_key(
        "auditlogeintrag_akteur_id_fkey", "auditlogeintrag", "user", ["akteur_id"], ["id"]
    )
