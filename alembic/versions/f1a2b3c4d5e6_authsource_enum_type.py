"""authsource_enum_type: fehlenden Postgres-ENUM-Typ fuer auth_source nachtragen

`e3f4a5b6c7d8` hat die Spalte `auth_source` als reines `sa.String()` angelegt,
waehrend das Model (`app/models/user.py`) sie als Python-Enum `AuthSource`
deklariert. SQLAlchemy castet Bind-Parameter fuer Enum-Spalten immer auf den
nativen Postgres-Typnamen (hier `authsource`, analog zu `role`/`roleenum` aus
der initialen Migration) - da dieser Typ nie per `CREATE TYPE` angelegt wurde,
schlaegt jedes INSERT/UPDATE auf `user.auth_source` mit
`UndefinedObjectError: type "authsource" does not exist` fehl (u.a. beim
Admin-Seeding beim Anwendungsstart).

Revision ID: f1a2b3c4d5e6
Revises: e3f4a5b6c7d8
Create Date: 2026-08-03 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUTHSOURCE = sa.Enum("local", "sso", name="authsource")


def upgrade() -> None:
    _AUTHSOURCE.create(op.get_bind(), checkfirst=True)
    op.execute('ALTER TABLE "user" ALTER COLUMN auth_source DROP DEFAULT')
    op.execute(
        'ALTER TABLE "user" ALTER COLUMN auth_source TYPE authsource USING auth_source::authsource'
    )
    op.execute("ALTER TABLE \"user\" ALTER COLUMN auth_source SET DEFAULT 'local'::authsource")


def downgrade() -> None:
    op.execute('ALTER TABLE "user" ALTER COLUMN auth_source DROP DEFAULT')
    op.execute(
        'ALTER TABLE "user" ALTER COLUMN auth_source TYPE VARCHAR USING auth_source::text'
    )
    op.execute("ALTER TABLE \"user\" ALTER COLUMN auth_source SET DEFAULT 'local'")
    _AUTHSOURCE.drop(op.get_bind(), checkfirst=True)
