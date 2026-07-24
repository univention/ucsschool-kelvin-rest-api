# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Execution-level tests for ``Operator.MATCHES_CI`` against the SQLite test DB.

Note: SQLite's ``LIKE`` is inherently case-insensitive for ASCII text, so most
assertions here would also pass with ``Operator.MATCHES`` by mistake — these
are a secondary smoke check, not proof of case-insensitivity itself. The
load-bearing proof is the Postgres-backed tests (docs/plan/context.md Risk 1;
docs/plan/tasks/011 and 012). The escaping assertions below are the exception:
they're dialect-independent and meaningful regardless of the SQLite caveat.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ucsschool_objects import Operator
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import FILTER_OPERATOR_BUILDERS
from ucsschool_objects.database_models import User as UserModel

from ...test_types import AsyncUserFactory


async def _names_matching(db_session: AsyncSession, pattern: str) -> set[str]:
    expr = FILTER_OPERATOR_BUILDERS[Operator.MATCHES_CI](UserModel.name, pattern)
    result = await db_session.execute(select(UserModel.name).where(expr))
    return set(result.scalars().all())


@pytest.mark.asyncio
async def test_matches_ci_leading_wildcard(
    db_session: AsyncSession, user_factory: AsyncUserFactory
) -> None:
    _ = await user_factory(name="John Doe")
    _ = await user_factory(name="Jane Roe")

    assert await _names_matching(db_session, "john*") == {"John Doe"}


@pytest.mark.asyncio
async def test_matches_ci_trailing_wildcard(
    db_session: AsyncSession, user_factory: AsyncUserFactory
) -> None:
    _ = await user_factory(name="John Doe")
    _ = await user_factory(name="Jane Roe")

    assert await _names_matching(db_session, "*DOE") == {"John Doe"}


@pytest.mark.asyncio
async def test_matches_ci_infix_wildcard(
    db_session: AsyncSession, user_factory: AsyncUserFactory
) -> None:
    _ = await user_factory(name="John Doe")
    _ = await user_factory(name="Jane Roe")

    assert await _names_matching(db_session, "*OHN DO*") == {"John Doe"}


@pytest.mark.asyncio
async def test_several_matches_with_wildcards(
    db_session: AsyncSession, user_factory: AsyncUserFactory
) -> None:
    _ = await user_factory(name="John Doe")
    _ = await user_factory(name="John Doerr")

    assert await _names_matching(db_session, "john*") == {"John Doe", "John Doerr"}


@pytest.mark.asyncio
async def test_matches_ci_no_wildcard_is_exact_match(
    db_session: AsyncSession, user_factory: AsyncUserFactory
) -> None:
    _ = await user_factory(name="John Doe")
    _ = await user_factory(name="John Doerr")

    assert await _names_matching(db_session, "JOHN DOE") == {"John Doe"}


@pytest.mark.asyncio
async def test_matches_ci_escapes_literal_percent_and_underscore(
    db_session: AsyncSession, user_factory: AsyncUserFactory
) -> None:
    """Dialect-independent: literal `%`/`_` in the search value must match literally,
    not be treated as SQL wildcards, regardless of any SQLite CI quirks."""
    _ = await user_factory(name="50%_off")
    _ = await user_factory(name="50Xoff")

    assert await _names_matching(db_session, "50%_off") == {"50%_off"}
