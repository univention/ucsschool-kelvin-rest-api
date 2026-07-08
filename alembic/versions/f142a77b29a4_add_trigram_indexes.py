"""add trigram indexes

Revision ID: f142a77b29a4
Revises: 62810ee19208
Create Date: 2026-07-08 00:00:00.000000

Adds the `pg_trgm` extension and GIN trigram indexes on the fixed set of
columns used for indexed case-insensitive wildcard search (`ILIKE`):
user.name, user.firstname, user.lastname, user.email, school.name,
group.name.

Uses plain `CREATE INDEX` (not `CONCURRENTLY`) deliberately, matching this
migration's raw-DDL style. This briefly locks writes to the affected tables
while the indexes are built. Deployments with very large `user`/`school`/`group`
tables should evaluate switching to `CREATE INDEX CONCURRENTLY` via
`op.get_context().autocommit_block()` before running this in production,
and validate that against the advisory-lock context manager in `alembic/env.py`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f142a77b29a4"
down_revision: str | Sequence[str] | None = "62810ee19208"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES = [
    ("ix_user_name_trgm", "user", "name"),
    ("ix_user_firstname_trgm", "user", "firstname"),
    ("ix_user_lastname_trgm", "user", "lastname"),
    ("ix_user_email_trgm", "user", "email"),
    ("ix_school_name_trgm", "school", "name"),
    ("ix_group_name_trgm", "group", "name"),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    for index_name, table, column in _INDEXES:
        op.execute(
            sa.text(
                f"CREATE INDEX IF NOT EXISTS {index_name} "
                f'ON "{table}" USING gin ("{column}" gin_trgm_ops)'
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    for index_name, _table, _column in _INDEXES:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))
    # Intentionally not dropping the pg_trgm extension: Task 007's dynamic
    # UDM-property indexes may depend on it, and migrations run linearly, so
    # dropping a shared extension here is unsafe.
