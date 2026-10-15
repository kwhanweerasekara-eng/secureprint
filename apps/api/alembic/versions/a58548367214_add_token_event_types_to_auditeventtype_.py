"""add token event types to auditeventtype enum

The api_tokens migration (ddb095e13734) added TOKEN_CREATED/TOKEN_REVOKED
to the Python AuditEventType enum, but never taught Postgres's native
auditeventtype enum type about them - autogenerate only diffs tables/columns,
never enum value sets. Every token create/revoke since then has 500'd when
apps.api.services.audit tried to log the event (psycopg2.errors.
InvalidTextRepresentation: invalid input value for enum auditeventtype).
The token row itself is created/deleted just fine beforehand (that commit
already happened), only the audit-log insert afterwards fails - which is why
tokens appeared to "not create" and deletes appeared to "need a refresh":
the frontend's request throws on the 500 and never gets to reload the list,
even though the underlying change already landed.

SQLite (local/test) never hits this: it has no native enum type, so a fresh
`Base.metadata.create_all()` always bakes in whatever the Python enum
currently defines. Only a Postgres database that reached ddb095e13734 via
`alembic upgrade` (i.e. any deployed environment) is affected.

Revision ID: a58548367214
Revises: ddb095e13734
Create Date: 2026-08-27 01:25:02.152015

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a58548367214'
down_revision: Union[str, None] = 'ddb095e13734'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'TOKEN_CREATED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'TOKEN_REVOKED'")


def downgrade() -> None:
    # Postgres does not support removing values from an enum type.
    pass
