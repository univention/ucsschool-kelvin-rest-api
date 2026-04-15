from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest
from tests.core.contracts.contract_test_support import (
    GroupQueryFactories,
    GroupQuerySetup,
    QueryExpectation,
    RoleQueryFactories,
    RoleQuerySetup,
    SchoolQueryFactories,
    SchoolQuerySetup,
    SearchReaderProtocol,
    UserQueryFactories,
    UserQuerySetup,
)
from ucsschool_objects.core.adapters.sqlalchemy import (
    SQLAlchemyGroupReader,
    SQLAlchemyRoleReader,
    SQLAlchemySchoolReader,
    SQLAlchemyUserReader,
)
from ucsschool_objects.core.domain import And, Filter, Not, Operator, Or, SearchQuery, SortSpec

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.test_types import (
        AsyncGroupFactory as GroupFactory,
        AsyncGroupTypeFactory as GroupTypeFactory,
        AsyncRoleFactory as RoleFactory,
        AsyncSchoolFactory as SchoolFactory,
        AsyncUserFactory as UserFactory,
    )


async def _setup_school_eq_case(factories: SchoolQueryFactories) -> QueryExpectation:
    await factories.school_factory(name="school-a")
    await factories.school_factory(name="school-b")
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="name", op=Operator.EQ, value="school-a")),
        expected_names=("school-a",),
    )


async def _setup_school_ne_case(factories: SchoolQueryFactories) -> QueryExpectation:
    await factories.school_factory(name="school-a")
    await factories.school_factory(name="school-b")
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="name", op=Operator.NE, value="school-a")),
        expected_names=("school-b",),
    )


async def _setup_school_in_case(factories: SchoolQueryFactories) -> QueryExpectation:
    await factories.school_factory(name="school-a")
    await factories.school_factory(name="school-b")
    await factories.school_factory(name="school-c")
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="name", op=Operator.IN, value=["school-a", "school-c"])),
        expected_names=("school-a", "school-c"),
    )


async def _setup_school_like_case(factories: SchoolQueryFactories) -> QueryExpectation:
    await factories.school_factory(name="alpha-campus")
    await factories.school_factory(name="beta-school")
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="name", op=Operator.LIKE, value="%school%")),
        expected_names=("beta-school",),
    )


async def _setup_group_eq_case(factories: GroupQueryFactories) -> QueryExpectation:
    workgroup_type = await factories.group_type_factory(name="workgroup")
    await factories.group_factory(name="group-a", group_type=workgroup_type)
    await factories.group_factory(name="group-b", group_type=workgroup_type)
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="name", op=Operator.EQ, value="group-a")),
        expected_names=("group-a",),
    )


async def _setup_group_ne_case(factories: GroupQueryFactories) -> QueryExpectation:
    workgroup_type = await factories.group_type_factory(name="workgroup")
    await factories.group_factory(name="group-a", group_type=workgroup_type)
    await factories.group_factory(name="group-b", group_type=workgroup_type)
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="name", op=Operator.NE, value="group-a")),
        expected_names=("group-b",),
    )


async def _setup_group_in_case(factories: GroupQueryFactories) -> QueryExpectation:
    workgroup_type = await factories.group_type_factory(name="workgroup")
    await factories.group_factory(name="group-a", group_type=workgroup_type)
    await factories.group_factory(name="group-b", group_type=workgroup_type)
    await factories.group_factory(name="group-c", group_type=workgroup_type)
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="name", op=Operator.IN, value=["group-a", "group-c"])),
        expected_names=("group-a", "group-c"),
    )


async def _setup_group_like_school_case(factories: GroupQueryFactories) -> QueryExpectation:
    workgroup_type = await factories.group_type_factory(name="workgroup")
    alpha_school = await factories.school_factory(name="alpha-school")
    beta_school = await factories.school_factory(name="beta-school")
    await factories.group_factory(name="group-a", school=alpha_school, group_type=workgroup_type)
    await factories.group_factory(name="group-b", school=beta_school, group_type=workgroup_type)
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="school_name", op=Operator.LIKE, value="alpha%")),
        expected_names=("group-a",),
    )


async def _setup_group_and_case(factories: GroupQueryFactories) -> QueryExpectation:
    workgroup_type = await factories.group_type_factory(name="workgroup")
    alpha_school = await factories.school_factory(name="alpha-school")
    beta_school = await factories.school_factory(name="beta-school")
    await factories.group_factory(name="group-a", school=alpha_school, group_type=workgroup_type)
    await factories.group_factory(name="group-b", school=alpha_school, group_type=workgroup_type)
    await factories.group_factory(name="group-c", school=beta_school, group_type=workgroup_type)
    return QueryExpectation(
        query=SearchQuery(
            where=And(
                clauses=(
                    Filter(field="school_name", op=Operator.LIKE, value="alpha%"),
                    Filter(field="name", op=Operator.EQ, value="group-a"),
                )
            )
        ),
        expected_names=("group-a",),
    )


async def _setup_group_or_case(factories: GroupQueryFactories) -> QueryExpectation:
    workgroup_type = await factories.group_type_factory(name="workgroup")
    school = await factories.school_factory(name="main-school")
    await factories.group_factory(name="group-a", school=school, group_type=workgroup_type)
    await factories.group_factory(name="group-b", school=school, group_type=workgroup_type)
    await factories.group_factory(name="group-c", school=school, group_type=workgroup_type)
    return QueryExpectation(
        query=SearchQuery(
            where=Or(
                clauses=(
                    Filter(field="name", op=Operator.EQ, value="group-a"),
                    Filter(field="name", op=Operator.EQ, value="group-c"),
                )
            )
        ),
        expected_names=("group-a", "group-c"),
    )


async def _setup_group_not_case(factories: GroupQueryFactories) -> QueryExpectation:
    workgroup_type = await factories.group_type_factory(name="workgroup")
    school = await factories.school_factory(name="main-school")
    await factories.group_factory(name="group-a", school=school, group_type=workgroup_type)
    await factories.group_factory(name="group-b", school=school, group_type=workgroup_type)
    return QueryExpectation(
        query=SearchQuery(where=Not(clause=Filter(field="name", op=Operator.EQ, value="group-a"))),
        expected_names=("group-b",),
    )


async def _setup_role_eq_case(factories: RoleQueryFactories) -> QueryExpectation:
    await factories.role_factory(name="school:admin")
    await factories.role_factory(name="school:teacher")
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="name", op=Operator.EQ, value="school:admin")),
        expected_names=("school:admin",),
    )


async def _setup_role_ne_case(factories: RoleQueryFactories) -> QueryExpectation:
    await factories.role_factory(name="school:admin")
    await factories.role_factory(name="school:teacher")
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="name", op=Operator.NE, value="school:admin")),
        expected_names=("school:teacher",),
    )


async def _setup_role_in_case(factories: RoleQueryFactories) -> QueryExpectation:
    await factories.role_factory(name="school:admin")
    await factories.role_factory(name="school:teacher")
    await factories.role_factory(name="school:student")
    return QueryExpectation(
        query=SearchQuery(
            where=Filter(
                field="name",
                op=Operator.IN,
                value=["school:admin", "school:student"],
            )
        ),
        expected_names=("school:admin", "school:student"),
    )


async def _setup_role_like_case(factories: RoleQueryFactories) -> QueryExpectation:
    await factories.role_factory(name="school:admin")
    await factories.role_factory(name="district:viewer")
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="name", op=Operator.LIKE, value="school:%")),
        expected_names=("school:admin",),
    )


async def _setup_user_eq_case(factories: UserQueryFactories) -> QueryExpectation:
    await factories.user_factory(name="anna")
    await factories.user_factory(name="bert")
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="name", op=Operator.EQ, value="anna")),
        expected_names=("anna",),
    )


async def _setup_user_ne_case(factories: UserQueryFactories) -> QueryExpectation:
    await factories.user_factory(name="active", active=True)
    await factories.user_factory(name="inactive", active=False)
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="active", op=Operator.NE, value=True)),
        expected_names=("inactive",),
    )


async def _setup_user_in_case(factories: UserQueryFactories) -> QueryExpectation:
    await factories.user_factory(name="anna")
    await factories.user_factory(name="bert")
    await factories.user_factory(name="carla")
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="name", op=Operator.IN, value=["anna", "carla"])),
        expected_names=("anna", "carla"),
    )


async def _setup_user_like_case(factories: UserQueryFactories) -> QueryExpectation:
    await factories.user_factory(name="anna", lastname="Miller")
    await factories.user_factory(name="bert", lastname="Schmidt")
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="lastname", op=Operator.LIKE, value="Mill%")),
        expected_names=("anna",),
    )


async def _setup_user_gt_case(factories: UserQueryFactories) -> QueryExpectation:
    await factories.user_factory(name="old", birthday=date(2000, 1, 1))
    await factories.user_factory(name="young", birthday=date(2015, 1, 1))
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="birthday", op=Operator.GT, value=date(2010, 1, 1))),
        expected_names=("young",),
    )


async def _setup_user_gte_case(factories: UserQueryFactories) -> QueryExpectation:
    await factories.user_factory(name="borderline", birthday=date(2010, 1, 1))
    await factories.user_factory(name="young", birthday=date(2015, 1, 1))
    await factories.user_factory(name="old", birthday=date(2000, 1, 1))
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="birthday", op=Operator.GTE, value=date(2010, 1, 1))),
        expected_names=("borderline", "young"),
    )


async def _setup_user_lt_case(factories: UserQueryFactories) -> QueryExpectation:
    await factories.user_factory(name="old", birthday=date(2000, 1, 1))
    await factories.user_factory(name="young", birthday=date(2015, 1, 1))
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="birthday", op=Operator.LT, value=date(2010, 1, 1))),
        expected_names=("old",),
    )


async def _setup_user_lte_case(factories: UserQueryFactories) -> QueryExpectation:
    await factories.user_factory(name="old", birthday=date(2000, 1, 1))
    await factories.user_factory(name="borderline", birthday=date(2010, 1, 1))
    await factories.user_factory(name="young", birthday=date(2015, 1, 1))
    return QueryExpectation(
        query=SearchQuery(where=Filter(field="birthday", op=Operator.LTE, value=date(2010, 1, 1))),
        expected_names=("borderline", "old"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup_case",
    [
        pytest.param(_setup_school_eq_case, id="school-eq"),
        pytest.param(_setup_school_ne_case, id="school-ne"),
        pytest.param(_setup_school_in_case, id="school-in"),
        pytest.param(_setup_school_like_case, id="school-like"),
    ],
)
async def test_school_query_operators(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    setup_case: SchoolQuerySetup,
) -> None:
    factories = SchoolQueryFactories(school_factory=school_factory)
    expectation = await setup_case(factories)
    reader = cast(SearchReaderProtocol, SQLAlchemySchoolReader(db_session))

    results = list(await reader.search(expectation.query, sort_by=expectation.sort_by))
    assert [item.name for item in results] == list(expectation.expected_names)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup_case",
    [
        pytest.param(_setup_group_eq_case, id="group-eq"),
        pytest.param(_setup_group_ne_case, id="group-ne"),
        pytest.param(_setup_group_in_case, id="group-in"),
        pytest.param(_setup_group_like_school_case, id="group-like-school"),
        pytest.param(_setup_group_and_case, id="group-and"),
        pytest.param(_setup_group_or_case, id="group-or"),
        pytest.param(_setup_group_not_case, id="group-not"),
    ],
)
async def test_group_query_operators(
    db_session: AsyncSession,
    group_factory: GroupFactory,
    group_type_factory: GroupTypeFactory,
    school_factory: SchoolFactory,
    setup_case: GroupQuerySetup,
) -> None:
    factories = GroupQueryFactories(
        school_factory=school_factory,
        group_factory=group_factory,
        group_type_factory=group_type_factory,
    )
    expectation = await setup_case(factories)
    reader = cast(SearchReaderProtocol, SQLAlchemyGroupReader(db_session))

    results = list(await reader.search(expectation.query, sort_by=expectation.sort_by))
    assert [item.name for item in results] == list(expectation.expected_names)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup_case",
    [
        pytest.param(_setup_role_eq_case, id="role-eq"),
        pytest.param(_setup_role_ne_case, id="role-ne"),
        pytest.param(_setup_role_in_case, id="role-in"),
        pytest.param(_setup_role_like_case, id="role-like"),
    ],
)
async def test_role_query_operators(
    db_session: AsyncSession,
    role_factory: RoleFactory,
    setup_case: RoleQuerySetup,
) -> None:
    factories = RoleQueryFactories(role_factory=role_factory)
    expectation = await setup_case(factories)
    reader = cast(SearchReaderProtocol, SQLAlchemyRoleReader(db_session))

    results = list(await reader.search(expectation.query, sort_by=expectation.sort_by))
    assert [item.name for item in results] == list(expectation.expected_names)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup_case",
    [
        pytest.param(_setup_user_eq_case, id="user-eq"),
        pytest.param(_setup_user_ne_case, id="user-ne"),
        pytest.param(_setup_user_in_case, id="user-in"),
        pytest.param(_setup_user_like_case, id="user-like"),
        pytest.param(_setup_user_gt_case, id="user-gt"),
        pytest.param(_setup_user_gte_case, id="user-gte"),
        pytest.param(_setup_user_lt_case, id="user-lt"),
        pytest.param(_setup_user_lte_case, id="user-lte"),
    ],
)
async def test_user_query_operators(
    db_session: AsyncSession,
    user_factory: UserFactory,
    setup_case: UserQuerySetup,
) -> None:
    factories = UserQueryFactories(user_factory=user_factory)
    expectation = await setup_case(factories)
    reader = cast(SearchReaderProtocol, SQLAlchemyUserReader(db_session))

    results = list(await reader.search(expectation.query, sort_by=expectation.sort_by))
    assert [item.name for item in results] == list(expectation.expected_names)


@pytest.mark.asyncio
async def test_query_negation_filters(db_session: AsyncSession, user_factory: UserFactory) -> None:
    await user_factory(name="active", active=True)
    await user_factory(name="inactive", active=False)
    reader = SQLAlchemyUserReader(db_session)

    q = SearchQuery(where=Not(clause=Filter(field="active", op=Operator.EQ, value=True)))
    results = await reader.search(q)
    assert [item.name for item in results] == ["inactive"]


@pytest.mark.asyncio
async def test_query_sort_and_pagination_deterministic(
    db_session: AsyncSession, school_factory: SchoolFactory
) -> None:
    await school_factory(name="s2")
    await school_factory(name="s1")
    await school_factory(name="s3")
    reader = SQLAlchemySchoolReader(db_session)

    ordered = list(
        await reader.search(sort_by=(SortSpec(field="name", ascending=True),), limit=10, offset=0)
    )
    assert [item.name for item in ordered] == ["s1", "s2", "s3"]

    page = list(
        await reader.search(sort_by=(SortSpec(field="name", ascending=True),), limit=2, offset=1)
    )
    assert [item.name for item in page] == ["s2", "s3"]


@pytest.mark.asyncio
async def test_query_sort_and_pagination_with_duplicate_sort_keys(
    db_session: AsyncSession, school_factory: SchoolFactory
) -> None:
    first = await school_factory(
        name="s1",
        class_share_file_server="same-server",
        public_id=UUID("00000000-0000-0000-0000-00000000000a"),
    )
    second = await school_factory(
        name="s2",
        class_share_file_server="same-server",
        public_id=UUID("00000000-0000-0000-0000-00000000000b"),
    )
    await school_factory(name="s3", class_share_file_server="zzz-server")
    reader = SQLAlchemySchoolReader(db_session)
    duplicate_public_ids = [str(first.public_id), str(second.public_id)]

    ordered = list(
        await reader.search(
            sort_by=(SortSpec(field="class_share_file_server", ascending=True),), limit=10, offset=0
        )
    )
    assert [str(item.public_id) for item in ordered[:2]] == duplicate_public_ids

    page = list(
        await reader.search(
            sort_by=(SortSpec(field="class_share_file_server", ascending=True),), limit=1, offset=1
        )
    )
    assert str(page[0].public_id) == duplicate_public_ids[1]
