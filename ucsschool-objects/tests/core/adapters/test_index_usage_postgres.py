# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""PostgreSQL query-plan tests for the user eager-load fan-out.

``GET /v2/users/<username>`` finds the user by a unique-indexed ``name``, but
then eager-loads its memberships, groups, wards and guardians with
``selectinload``. Two of those probe an association table on the column its
composite primary key does *not* lead with, which no index covered: the read
degenerated into a sequential scan of the whole association table on every
single-user request.

What is asserted here is that PostgreSQL *can* reach those rows through an
index, using the statements SQLAlchemy actually emits rather than hand-written
approximations -- so the test keeps following the loader options in
``user_manager.py`` if they change.

``enable_seqscan`` is turned off for the assertion on purpose. On a table
holding a handful of seeded rows the planner will sequentially scan whatever
indexes exist, because that genuinely is cheaper; without the setting the test
would have to seed tens of thousands of rows to assert anything at all. With
it, the planner falls back to a sequential scan only when no index *can* serve
the predicate -- which is exactly the property under test. ``SET LOCAL`` is
safe because the fixture rolls its transaction back.

Both ``Index Scan`` and ``Index Only Scan`` are accepted: index-only requires
a current visibility map, which a table seeded inside the test transaction
does not have.

Requires PostgreSQL. ``postgres_db_url`` skips when ``CI=true`` and
``CORELIB_POSTGRES_TEST_URL`` is unset, so in CI this is currently a no-op and
the dialect-neutral guard in
``tests/test_database_models/test_indexes.py`` is what protects the indexes
there. Run locally with Docker available to exercise the planner.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import select
from ucsschool_objects.database_models import Group as GroupModel, SchoolMembership, User as UserModel

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.ext.asyncio import AsyncSession

    from ...test_types import (
        AsyncGroupFactory,
        AsyncSchoolMembershipFactory,
        AsyncUserFactory,
    )

pytestmark = pytest.mark.asyncio

_ASSOCIATION_TABLES = (
    "group_member_association",
    "legal_guardian_association",
)


class _StatementRecorder:
    """Collect the SQL SQLAlchemy emits, with the parameters it binds."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, Any]] = []

    def __call__(
        self,
        _conn: Any,
        _cursor: Any,
        statement: str,
        parameters: Any,
        _context: Any,
        _executemany: bool,  # noqa: FBT001
    ) -> None:
        self.statements.append((statement, parameters))

    def touching(self, table: str) -> list[tuple[str, Any]]:
        return [(sql, params) for sql, params in self.statements if table in sql]


@pytest.fixture
def recorder() -> Iterator[_StatementRecorder]:
    recorder = _StatementRecorder()
    event.listen(Engine, "before_cursor_execute", recorder)
    try:
        yield recorder
    finally:
        event.remove(Engine, "before_cursor_execute", recorder)


def _scanned_sequentially(plan: dict[str, Any], table: str) -> bool:
    if plan.get("Node Type") == "Seq Scan" and plan.get("Relation Name") == table:
        return True
    return any(_scanned_sequentially(child, table) for child in plan.get("Plans", []))


def _indexes_used(plan: dict[str, Any]) -> set[str]:
    used = {plan["Index Name"]} if "Index Name" in plan else set()
    for child in plan.get("Plans", []):
        used |= _indexes_used(child)
    return used


async def _explain(session: AsyncSession, statement: str, parameters: Any) -> dict[str, Any]:
    connection = await session.connection()
    result = await connection.exec_driver_sql(
        f"EXPLAIN (FORMAT JSON) {statement}",
        parameters,
    )
    plan = result.scalar_one()
    if isinstance(plan, str):
        plan = json.loads(plan)
    return plan[0]["Plan"]


async def _seed(
    session: AsyncSession,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
    school_membership_factory: AsyncSchoolMembershipFactory,
) -> str:
    """Create a user that has both a group membership and a legal guardian.

    Relations are passed as factory overrides so they reach the model
    constructor while the instance is still pending: assigning to them
    afterwards would trip the ``lazy="raise"`` guard on the collection.
    """
    guardian = await user_factory(db_session=session)
    ward = await user_factory(db_session=session, legal_guardians=[guardian])
    group = await group_factory(db_session=session)
    _ = await school_membership_factory(db_session=session, user=ward, groups=[group])
    await session.flush()
    return ward.name


@pytest.mark.parametrize(
    "table,index_name",
    [
        (
            "group_member_association",
            "ix_group_member_association_school_membership_id_group_id",
        ),
        (
            "legal_guardian_association",
            "ix_legal_guardian_association_legal_ward_id_legal_guardian_id",
        ),
    ],
)
async def test_user_eager_load_reaches_associations_by_index(
    postgres_db_session: AsyncSession,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
    school_membership_factory: AsyncSchoolMembershipFactory,
    recorder: _StatementRecorder,
    table: str,
    index_name: str,
) -> None:
    username = await _seed(postgres_db_session, user_factory, group_factory, school_membership_factory)
    for association_table in _ASSOCIATION_TABLES:
        await postgres_db_session.execute(text(f"ANALYZE {association_table}"))
    await postgres_db_session.execute(text("SET LOCAL enable_seqscan = off"))

    recorder.statements.clear()
    postgres_db_session.expunge_all()
    statement = (
        select(UserModel)
        .where(UserModel.name == username)
        .options(
            selectinload(UserModel.school_memberships)
            .selectinload(SchoolMembership.groups)
            .selectinload(GroupModel.roles),
            selectinload(UserModel.legal_guardians),
            selectinload(UserModel.legal_wards),
        )
    )
    _ = (await postgres_db_session.execute(statement)).scalars().all()

    emitted = recorder.touching(table)
    assert emitted, f"the eager load never touched {table}; the loader options changed"
    for sql, parameters in emitted:
        plan = await _explain(postgres_db_session, sql, parameters)
        assert not _scanned_sequentially(plan, table), (
            f"{table} is scanned sequentially even with enable_seqscan off, so no "
            f"index serves this predicate:\n{sql}"
        )
        assert index_name in _indexes_used(plan), (
            f"expected {index_name} in the plan for:\n{sql}\nused: {sorted(_indexes_used(plan))}"
        )
