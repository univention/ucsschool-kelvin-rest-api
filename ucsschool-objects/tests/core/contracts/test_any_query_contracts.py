# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from ucsschool_objects import (
    And,
    Any,
    Filter,
    InvalidAnyClause,
    Not,
    Operator,
    Or,
    SearchQuery,
    SortSpec,
    UnsupportedFilterField,
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


def _role(name: str) -> Filter:
    return Filter(field="roles.name", op=Operator.EQ, value=name)


def _school(name: str) -> Filter:
    return Filter(field="schools.name", op=Operator.EQ, value=name)


def _school_role(pattern: str) -> Any:
    return Any(Filter(field="school_roles", op=Operator.MATCHES_CI, value=pattern))


def _role_at_school(role: str, school: str) -> Any:
    return Any(
        And(
            (
                Filter(field="roles.name", op=Operator.MATCHES_CI, value=role),
                Filter(field="schools.name", op=Operator.MATCHES_CI, value=school),
            )
        )
    )


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
async def seeded_users(
    user_factory: UserFactory,
    school_membership_factory: SchoolMembershipFactory,
    school_x: SchoolModel,
    school_y: SchoolModel,
    roles: dict[str, RoleModel],
) -> None:
    memberships = {
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
@pytest.mark.usefixtures("seeded_users")
@pytest.mark.parametrize(
    ("where", "expected_names"),
    [
        pytest.param(
            Any(_role("teacher")),
            ["student-x-teacher-y", "teacher", "teacher-staff"],
            id="single",
        ),
        pytest.param(
            Any(Or((_role("staff"), _role("student")))),
            ["student-x-teacher-y", "teacher-staff"],
            id="or",
        ),
        pytest.param(
            And((Any(_role("teacher")), Any(_role("staff")))),
            ["teacher-staff"],
            id="and-of-any",
        ),
        pytest.param(Any(And((_role("teacher"), _role("staff")))), [], id="and-inside-any"),
        pytest.param(
            Not(Any(_role("teacher"))),
            ["nobody"],
            id="not-any",
        ),
        pytest.param(
            Any(And((_school("school-x"), _role("teacher")))),
            ["teacher", "teacher-staff"],
            id="same-membership",
        ),
        pytest.param(
            And((_school("school-x"), Any(And((_school("school-y"), _role("teacher")))))),
            ["student-x-teacher-y"],
            id="next-to-outer-school-filter",
        ),
        pytest.param(
            And((Filter(field="name", op=Operator.NE, value="teacher"), Any(_role("teacher")))),
            ["student-x-teacher-y", "teacher-staff"],
            id="next-to-scalar-filter",
        ),
        pytest.param(
            _school_role("teacher:school:school-x"),
            ["teacher", "teacher-staff"],
            id="exact",
        ),
        pytest.param(
            And((_school_role("teacher:school:school-x"), _school_role("staff:school:school-x"))),
            ["teacher-staff"],
            id="and",
        ),
        pytest.param(
            And((_school_role("student:school:school-x"), _school_role("teacher:school:school-y"))),
            ["student-x-teacher-y"],
            id="across-schools",
        ),
        pytest.param(
            _school_role("teacher:school:school-y"), ["student-x-teacher-y"], id="school-scope"
        ),
        pytest.param(
            _school_role("teacher:school:*"),
            ["student-x-teacher-y", "teacher", "teacher-staff"],
            id="wildcard-school",
        ),
        pytest.param(
            _school_role("*:school:school-y"),
            ["student-x-teacher-y"],
            id="wildcard-role",
        ),
        pytest.param(
            _school_role("*"),
            ["student-x-teacher-y", "teacher", "teacher-staff"],
            id="wildcard-only",
        ),
        pytest.param(
            _school_role("TEACHER:School:SCHOOL-X"),
            ["teacher", "teacher-staff"],
            id="case-insensitive",
        ),
        pytest.param(_school_role("teacher:school:school_x"), [], id="literal-underscore"),
        pytest.param(_school_role("teacher:school:school%"), [], id="literal-percent"),
        pytest.param(_school_role("teacher:exam:school-x"), [], id="other-context"),
        pytest.param(_school_role(""), [], id="empty"),
        pytest.param(
            And((_school("school-x"), _school_role("teacher:school:school-y"))),
            ["student-x-teacher-y"],
            id="school-roles-next-to-outer-school-filter",
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
async def test_user_school_roles_are_rejected_outside_any(db_session: AsyncSession) -> None:
    manager = SQLAlchemyUserManager(db_session)

    with pytest.raises(UnsupportedFilterField):
        await manager.search(
            SearchQuery(where=Filter(field="school_roles", op=Operator.EQ, value="teacher:school:x"))
        )


@pytest.mark.asyncio
@pytest.mark.usefixtures("seeded_users")
async def test_user_any_query_pages_without_duplicates(db_session: AsyncSession) -> None:
    manager = SQLAlchemyUserManager(db_session)
    query = SearchQuery(where=Any(Or((_role("teacher"), _role("staff")))))
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
        pytest.param(Any(Filter(field="name", op=Operator.EQ, value="x")), id="scalar-field"),
        pytest.param(
            Any(Filter(field="udm_properties.title", op=Operator.EQ, value="x")),
            id="json-field",
        ),
        pytest.param(Any(Any(_role("teacher"))), id="nested-any"),
        pytest.param(Any(And((_role("teacher"), Any(_role("staff"))))), id="deeply-nested-any"),
    ],
)
async def test_user_any_query_rejects_invalid_clauses(
    db_session: AsyncSession, where: QueryExpr
) -> None:
    manager = SQLAlchemyUserManager(db_session)

    with pytest.raises(InvalidAnyClause):
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

    with pytest.raises(InvalidAnyClause):
        await manager.search(SearchQuery(where=Any(Filter(field=field, op=Operator.EQ, value="x"))))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("school_pattern", "expected_names"),
    [
        pytest.param(r"a\b_c%d", ["literal"], id="exact"),
        pytest.param(r"a\b_c*", ["literal"], id="wildcard"),
        pytest.param(r"a\bxc%d", [], id="underscore-is-literal"),
        pytest.param(r"a\b_cxd", [], id="percent-is-literal"),
        pytest.param(r"ab_c%d", [], id="backslash-is-literal"),
    ],
)
async def test_user_any_query_matches_like_metacharacters_literally(
    db_session: AsyncSession,
    user_factory: UserFactory,
    school_factory: SchoolFactory,
    role_factory: RoleFactory,
    school_membership_factory: SchoolMembershipFactory,
    school_pattern: str,
    expected_names: list[str],
) -> None:
    school = await school_factory(name=r"a\b_c%d")
    teacher = await role_factory(name="teacher")
    user = await user_factory(name="literal")
    await school_membership_factory(user=user, school=school, is_primary=True, roles=[teacher])
    manager = SQLAlchemyUserManager(db_session)

    results = await manager.search(SearchQuery(where=_role_at_school("teacher", school_pattern)))

    assert [found.name for found in results] == expected_names


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "where",
    [
        pytest.param(_role_at_school("*", "*"), id="split"),
        pytest.param(_school_role("*"), id="school-roles"),
    ],
)
async def test_user_any_query_needs_a_role_on_the_membership(
    db_session: AsyncSession,
    user_factory: UserFactory,
    school_factory: SchoolFactory,
    role_factory: RoleFactory,
    school_membership_factory: SchoolMembershipFactory,
    where: QueryExpr,
) -> None:
    school = await school_factory(name="school-x")
    teacher = await role_factory(name="teacher")
    with_role = await user_factory(name="with-role")
    without_role = await user_factory(name="without-role")
    await school_membership_factory(user=with_role, school=school, is_primary=True, roles=[teacher])
    await school_membership_factory(user=without_role, school=school, is_primary=True, roles=[])
    manager = SQLAlchemyUserManager(db_session)

    results = await manager.search(SearchQuery(where=where))

    assert [found.name for found in results] == ["with-role"]
