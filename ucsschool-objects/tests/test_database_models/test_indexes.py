# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Indexes that no query in this package names explicitly, but every
case-insensitive username lookup depends on."""

from __future__ import annotations

from ucsschool_objects.database_models import User


def test_user_name_has_an_index_on_its_lowercase_form() -> None:
    """``Operator.IN_CI`` compares ``lower(name)``.

    The unique index on ``name`` does not serve that comparison, so without
    this index every such lookup reads the whole table: measured at 100k
    users, a single username takes 33 ms instead of 0.04 ms.
    """
    user_table = User.metadata.tables[User.__tablename__]
    assert "ix_user_name_lower" in {index.name for index in user_table.indexes}
