# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from ucsschool_objects import (
    And,
    AnyRelated,
    Filter,
    InvalidAnyRelatedClause,
    Not,
    Operator,
    Or,
    SearchQuery,
    SortSpec,
    UnsupportedQueryExpression,
)
from ucsschool_objects.core.adapters.sqlalchemy import (
    SQLAlchemyGroupManager,
    SQLAlchemyRoleManager,
    SQLAlchemySchoolManager,
    SQLAlchemyUserManager,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.test_types import (
        AsyncRoleFactory as RoleFactory,
        AsyncSchoolFactory as SchoolFactory,
        AsyncSchoolMembershipFactory as SchoolMembershipFactory,
        AsyncUserFactory as UserFactory,
    )
    from ucsschool_objects import QueryExpr
    from ucsschool_objects.database_models import Role as RoleModel, School as SchoolModel


_UNKNOWN = cast("QueryExpr", object())


def _role(name: str) -> Filter:
    return Filter(field="roles.name", op=Operator.EQ, value=name)


def _school(name: str) -> Filter:
    return Filter(field="schools.name", op=Operator.EQ, value=name)


@pytest.fixture
async def school_x(school_factory: SchoolFactory) -> SchoolModel:
    return await school_factory(name="school-x")


@pytest.fixture
async def school_y(school_factory: SchoolFactory) -> SchoolModel:
    return await school_factory(name="school-y")


@pytest.fixture
async def roles(role_factory: RoleFactory) -> dict[str, RoleModel]:
    return {name: await role_factory(name=name) for name in ("teacher", "staff", "student")}


@pytest.fixture
async def users(
    user_factory: UserFactory,
    school_membership_factory: SchoolMembershipFactory,
    school_x: SchoolModel,
    school_y: SchoolModel,
    roles: dict[str, RoleModel],
) -> None:
    memberships: dict[str, list[tuple[SchoolModel, tuple[str, ...]]]] = {
        "teacher-staff": [(school_x, ("teacher", "staff"))],
        "teacher": [(school_x, ("teacher",))],
        "student-x-teacher-y": [(school_x, ("student",)), (school_y, ("teacher",))],
        "nobody": [],
    }
    for user_name, user_memberships in memberships.items():
        user = await user_factory(name=user_name)
        for index, (school, role_names) in enumerate(user_memberships):
            await school_membership_factory(
                user=user,
                school=school,
                is_primary=index == 0,
                roles=[roles[name] for name in role_names],
            )


@pytest.mark.asyncio
@pytest.mark.usefixtures("users")
@pytest.mark.parametrize(
    ("where", "expected_names"),
    [
        pytest.param(
            AnyRelated(_role("teacher")),
            ["student-x-teacher-y", "teacher", "teacher-staff"],
            id="single",
        ),
        pytest.param(
            AnyRelated(Or((_role("staff"), _role("student")))),
            ["student-x-teacher-y", "teacher-staff"],
            id="or",
        ),
        pytest.param(
            And((AnyRelated(_role("teacher")), AnyRelated(_role("staff")))),
            ["teacher-staff"],
            id="and-of-any",
        ),
        pytest.param(AnyRelated(And((_role("teacher"), _role("staff")))), [], id="and-inside-any"),
        pytest.param(
            Not(AnyRelated(_role("teacher"))),
            ["nobody"],
            id="not-any",
        ),
        pytest.param(
            AnyRelated(And((_school("school-x"), _role("teacher")))),
            ["teacher", "teacher-staff"],
            id="same-membership",
        ),
        pytest.param(
            And((_school("school-x"), AnyRelated(And((_school("school-y"), _role("teacher")))))),
            ["student-x-teacher-y"],
            id="next-to-outer-school-filter",
        ),
        pytest.param(
            And((Filter(field="name", op=Operator.NE, value="teacher"), AnyRelated(_role("teacher")))),
            ["student-x-teacher-y", "teacher-staff"],
            id="next-to-scalar-filter",
        ),
    ],
)
async def test_user_any_query(
    db_session: AsyncSession, where: QueryExpr, expected_names: list[str]
) -> None:
    manager = SQLAlchemyUserManager(db_session)

    results = await manager.search(SearchQuery(where=where), sort_by=(SortSpec(field="name"),))

    assert [user.name for user in results] == expected_names


@pytest.mark.asyncio
@pytest.mark.usefixtures("users")
async def test_user_any_query_pages_without_duplicates(db_session: AsyncSession) -> None:
    manager = SQLAlchemyUserManager(db_session)
    query = SearchQuery(where=AnyRelated(Or((_role("teacher"), _role("staff")))))
    sort_by = (SortSpec(field="name"),)

    names: list[str] = []
    search_after: tuple[str, ...] | None = None
    while page := list(await manager.search(query, sort_by=sort_by, search_after=search_after, limit=1)):
        names.extend(user.name for user in page)
        search_after = (page[-1].name,)

    assert names == ["student-x-teacher-y", "teacher", "teacher-staff"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "where",
    [
        pytest.param(AnyRelated(Filter(field="name", op=Operator.EQ, value="x")), id="scalar-field"),
        pytest.param(
            AnyRelated(Filter(field="udm_properties.title", op=Operator.EQ, value="x")),
            id="json-field",
        ),
        pytest.param(AnyRelated(AnyRelated(_role("teacher"))), id="nested-any"),
        pytest.param(
            AnyRelated(And((_role("teacher"), AnyRelated(_role("staff"))))), id="deeply-nested-any"
        ),
    ],
)
async def test_user_any_query_rejects_invalid_clauses(
    db_session: AsyncSession, where: QueryExpr
) -> None:
    manager = SQLAlchemyUserManager(db_session)

    with pytest.raises(InvalidAnyRelatedClause):
        await manager.search(SearchQuery(where=where))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("manager_cls", "field"),
    [
        pytest.param(SQLAlchemyGroupManager, "roles.name", id="group"),
        pytest.param(SQLAlchemySchoolManager, "name", id="school"),
        pytest.param(SQLAlchemyRoleManager, "name", id="role"),
    ],
)
async def test_any_query_is_rejected_by_other_managers(
    db_session: AsyncSession,
    manager_cls: type[SQLAlchemyGroupManager | SQLAlchemySchoolManager | SQLAlchemyRoleManager],
    field: str,
) -> None:
    manager = manager_cls(db_session)

    with pytest.raises(InvalidAnyRelatedClause):
        await manager.search(
            SearchQuery(where=AnyRelated(Filter(field=field, op=Operator.EQ, value="x")))
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "where",
    [
        pytest.param(_UNKNOWN, id="top-level"),
        pytest.param(And((_role("teacher"), _UNKNOWN)), id="nested"),
        pytest.param(AnyRelated(Not(_UNKNOWN)), id="inside-any"),
    ],
)
async def test_query_rejects_unknown_expressions(db_session: AsyncSession, where: QueryExpr) -> None:
    manager = SQLAlchemyUserManager(db_session)

    with pytest.raises(UnsupportedQueryExpression):
        await manager.search(SearchQuery(where=where))
