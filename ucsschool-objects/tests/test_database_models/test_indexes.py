# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Regression guard for the reverse-direction association indexes.

A composite primary key only serves lookups that lead with its first column.
Both association tables below are read from *both* directions by the eager
loads of ``GET /v2/users/<username>``, so the direction the primary key does
not cover needs an index of its own -- without it the read fans out into a
sequential scan of the whole association table on every request.

These assertions run against the ORM metadata as materialised by
``Base.metadata.create_all``, so they are dialect-neutral and hold on SQLite.
They deliberately check the *declared* index rather than a query plan: what
can regress here is someone dropping the ``__table_args__`` from
``database_models.py``. Whether PostgreSQL then picks the index is asserted
separately, in ``tests/core/adapters/test_index_usage_postgres.py``.

The column order matters as much as the presence: the probed column has to
lead, and the trailing column is the join key, which lets PostgreSQL satisfy
the association side with an index-only scan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import inspect

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
    from sqlalchemy.engine.interfaces import ReflectedIndex
    from sqlalchemy.ext.asyncio import AsyncEngine

_EXPECTED_INDEXES = [
    (
        "group_member_association",
        "ix_group_member_association_school_membership_id_group_id",
        ["school_membership_id", "group_id"],
    ),
    (
        "legal_guardian_association",
        "ix_legal_guardian_association_legal_ward_id_legal_guardian_id",
        ["legal_ward_id", "legal_guardian_id"],
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "table_name,index_name,expected_columns",
    _EXPECTED_INDEXES,
    ids=[table_name for table_name, _index_name, _columns in _EXPECTED_INDEXES],
)
async def test_reverse_association_index_exists(
    db_engine: AsyncEngine,
    table_name: str,
    index_name: str,
    expected_columns: list[str],
) -> None:
    def _indexes(connection: Connection) -> list[ReflectedIndex]:
        return inspect(connection).get_indexes(table_name)

    async with db_engine.connect() as connection:
        indexes = await connection.run_sync(_indexes)

    by_name = {index["name"]: index for index in indexes}
    assert index_name in by_name, (
        f"{table_name} is missing {index_name!r}; the reverse lookup direction "
        f"would fall back to a sequential scan. Found: {sorted(n for n in by_name if n)}"
    )
    index = by_name[index_name]
    assert index["column_names"] == expected_columns
    # The primary key already enforces uniqueness of the pair; a second unique
    # index would only add an enforcement check on the connector's write path.
    assert not index.get("unique")
