# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""add reverse association indexes

Index the two association-table lookups that ``GET /v2/users/<username>``
performs but no index covered.

A composite primary key only serves lookups that lead with its first column.
``group_member_association`` is keyed ``(group_id, school_membership_id)`` and
``legal_guardian_association`` ``(legal_guardian_id, legal_ward_id)``, so the
``Group.members`` and ``User.legal_wards`` directions are covered while the
reverse directions are not. The eager load of a single user probes exactly
those reverse directions -- ``SchoolMembership.groups`` by
``school_membership_id`` and ``User.legal_guardians`` by ``legal_ward_id`` --
and therefore sequentially scanned both tables on every request.

Both indexes are composite in ``(probed column, join key)`` order so the
association side can be read with an index-only scan: the tables have exactly
two columns, so the index is no wider than the heap tuple. Both are
non-unique; the primary key already enforces the pair, and a second unique
index would only add an enforcement check on the connector's insert path.

Deliberately not indexed here: the ``role_id`` columns of
``group_role_association``, ``group_member_role_association`` and
``school_membership_role_association``. Their only consumer would be the
foreign-key check of ``DELETE FROM role``; ``role`` holds nine seeded rows,
the ``v2`` role router exposes no DELETE route, and ``role_id`` has about nine
distinct values. Every read direction of those tables is already served by the
leading primary-key column, so the indexes would be write overhead only.

The indexes are declared in the ORM metadata as well (``database_models.py``),
both so that ``--autogenerate`` does not propose dropping them and so that the
test fixtures, which build their schema with ``Base.metadata.create_all``
rather than with Alembic, see them.

Built with ``CREATE INDEX CONCURRENTLY``, unlike the trigram indexes of the
init revision: this revision runs against a populated database, where a plain
``CREATE INDEX`` would hold a write lock on ``group_member_association`` for
the whole build and stall the Kelvin connector. The cost is that the DDL runs
outside the migration transaction (``autocommit_block`` commits it and opens a
new one). The advisory lock in ``alembic/env.py`` is unaffected, because
``pg_try_advisory_lock`` is session-scoped and ``autocommit_block`` only
changes the isolation level of the same connection.

A failed ``CREATE INDEX CONCURRENTLY`` leaves an **invalid** index behind,
which the planner ignores and which ``if_not_exists`` would silently skip on a
re-run. ``upgrade()`` therefore drops invalid leftovers of its own indexes
before creating them. To check by hand::

    SELECT c.relname FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
    WHERE NOT i.indisvalid;

An operator who wants to run the DDL out of band can start Kelvin with
``SKIP_UCSSCHOOL_KELVIN_DB_MIGRATION=true``, create the indexes with ``psql``
and then ``alembic --config pyproject.toml stamp head``.

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

    Offline (``--sql``) runs cannot inspect the catalog, so they skip this and
    emit a reminder instead; concurrent index builds are not possible from a
    generated script either.
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
