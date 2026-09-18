# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""add reverse association indexes

A composite primary key only serves lookups that lead with its first column.
``group_member_association`` is keyed ``(group_id, school_membership_id)`` and
``legal_guardian_association`` ``(legal_guardian_id, legal_ward_id)``, so the
reverse directions, which the eager load of ``GET /v2/users/<username>``
probes, scanned both tables sequentially. Both new indexes lead with the
probed column and trail the join key, so the association side can be read
index-only. They are declared in ``database_models.py`` as well, so that
``--autogenerate`` keeps them and the test fixtures see them.

Built concurrently because this revision runs against a populated database. A
failed concurrent build leaves an invalid index behind that the planner
ignores and ``if_not_exists`` would skip, so ``upgrade()`` drops invalid
leftovers first.

Revision ID: e3d39f016714
Revises: e49791148e25
Create Date: 2026-09-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3d39f016714"
down_revision: str | Sequence[str] | None = "e49791148e25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES: list[tuple[str, str, list[str]]] = [
    (
        "ix_group_member_association_school_membership_id_group_id",
        "group_member_association",
        ["school_membership_id", "group_id"],
    ),
    (
        "ix_legal_guardian_association_legal_ward_id_legal_guardian_id",
        "legal_guardian_association",
        ["legal_ward_id", "legal_guardian_id"],
    ),
]

_INVALID_INDEX_QUERY = sa.text(
    "SELECT c.relname FROM pg_class c"
    " JOIN pg_index i ON i.indexrelid = c.oid"
    " WHERE c.relname = ANY(:names) AND NOT i.indisvalid"
)


def _drop_invalid_leftovers() -> None:
    """Remove invalid indexes left behind by an interrupted concurrent build.

    Offline (``--sql``) runs cannot inspect the catalog and emit a reminder
    instead.
    """
    context = op.get_context()
    if context.as_sql:
        op.execute("-- check pg_index.indisvalid for leftovers of an aborted build")
        return
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    names = [index_name for index_name, _table, _columns in _INDEXES]
    invalid = bind.execute(_INVALID_INDEX_QUERY, {"names": names}).scalars().all()
    for index_name in invalid:
        op.execute(sa.text(f'DROP INDEX CONCURRENTLY IF EXISTS "{index_name}"'))


def upgrade() -> None:
    """Upgrade schema."""
    with op.get_context().autocommit_block():
        _drop_invalid_leftovers()
        for index_name, table, columns in _INDEXES:
            op.create_index(
                index_name,
                table,
                columns,
                if_not_exists=True,
                postgresql_concurrently=True,
            )


def downgrade() -> None:
    """Downgrade schema."""
    with op.get_context().autocommit_block():
        for index_name, table, _columns in reversed(_INDEXES):
            op.drop_index(
                index_name,
                table_name=table,
                if_exists=True,
                postgresql_concurrently=True,
            )
