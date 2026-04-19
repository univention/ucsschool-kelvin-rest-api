from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING, cast

import pytest
from tests.core.contracts.contract_test_support import (
    ReaderContractFactories,
    ReaderProtocol,
    ReaderSearchExpectation,
    ReaderSetup,
)
from ucsschool_objects.core.adapters.sqlalchemy import (
    SQLAlchemyGroupReader,
    SQLAlchemyRoleReader,
    SQLAlchemySchoolReader,
    SQLAlchemyUserReader,
)
from ucsschool_objects.core.domain import (
    Filter,
    LoadSpec,
    Operator,
    SearchQuery,
    SortSpec,
    UnloadedType,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.test_types import (
        AsyncGroupFactory as GroupFactory,
        AsyncGroupTypeFactory as GroupTypeFactory,
        AsyncRoleFactory as RoleFactory,
        AsyncSchoolFactory as SchoolFactory,
        AsyncSchoolMembershipFactory as SchoolMembershipFactory,
        AsyncUserFactory as UserFactory,
    )


async def _setup_school_reader_case(factories: ReaderContractFactories) -> ReaderSearchExpectation:
    school = await factories.school_factory(name="school-1")
    return ReaderSearchExpectation(
        public_id=school.public_id,
        expected_name="school-1",
        query=SearchQuery(where=Filter(field="name", op=Operator.EQ, value="school-1")),
    )


def _build_group_reader_case(group_type_name: str, group_name: str) -> ReaderSetup:
    async def _setup_group_reader_case(factories: ReaderContractFactories) -> ReaderSearchExpectation:
        group_type = await factories.group_type_factory(name=group_type_name)
        group = await factories.group_factory(name=group_name, group_type=group_type)
        return ReaderSearchExpectation(
            public_id=group.public_id,
            expected_name=group_name,
            query=SearchQuery(where=Filter(field="name", op=Operator.EQ, value=group_name)),
        )

    return _setup_group_reader_case


async def _setup_role_reader_case(factories: ReaderContractFactories) -> ReaderSearchExpectation:
    role = await factories.role_factory(name="school:admin")
    return ReaderSearchExpectation(
        public_id=role.public_id,
        expected_name="school:admin",
        query=SearchQuery(where=Filter(field="name", op=Operator.EQ, value="school:admin")),
    )


async def _setup_user_reader_case(factories: ReaderContractFactories) -> ReaderSearchExpectation:
    user = await factories.user_factory(name="anna")
    return ReaderSearchExpectation(
        public_id=user.public_id,
        expected_name="anna",
        query=SearchQuery(where=Filter(field="name", op=Operator.EQ, value="anna")),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reader_cls, setup_case",
    [
        pytest.param(SQLAlchemySchoolReader, _setup_school_reader_case, id="school"),
        pytest.param(
            SQLAlchemyGroupReader,
            _build_group_reader_case("school_class", "class-a"),
            id="group-school-class",
        ),
        pytest.param(
            SQLAlchemyGroupReader,
            _build_group_reader_case("workgroup", "admins"),
            id="group-workgroup",
        ),
        pytest.param(SQLAlchemyRoleReader, _setup_role_reader_case, id="role"),
        pytest.param(SQLAlchemyUserReader, _setup_user_reader_case, id="user"),
    ],
)
async def test_reader_get_and_search_contract(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
    group_type_factory: GroupTypeFactory,
    role_factory: RoleFactory,
    user_factory: UserFactory,
    reader_cls: Callable[[AsyncSession], object],
    setup_case: ReaderSetup,
) -> None:
    factories = ReaderContractFactories(
        school_factory=school_factory,
        group_factory=group_factory,
        group_type_factory=group_type_factory,
        role_factory=role_factory,
        user_factory=user_factory,
    )
    expectation = await setup_case(factories)
    reader = cast(ReaderProtocol, reader_cls(db_session))

    fetched = await reader.get(expectation.public_id)
    assert fetched.name == expectation.expected_name

    results = list(await reader.search(expectation.query))
    assert len(results) == 1
    assert results[0].public_id == expectation.public_id


@pytest.mark.asyncio
async def test_group_reader_supports_sorting_by_school_fields(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
    group_type_factory: GroupTypeFactory,
) -> None:
    workgroup_type = await group_type_factory(name="workgroup")
    school_a = await school_factory(name="alpha")
    school_b = await school_factory(name="beta")
    await group_factory(name="group-b", school=school_b, group_type=workgroup_type)
    await group_factory(name="group-a", school=school_a, group_type=workgroup_type)
    reader = SQLAlchemyGroupReader(db_session)

    results = list(await reader.search(sort_by=(SortSpec(field="school_name", ascending=True),)))
    assert [item.name for item in results] == ["group-a", "group-b"]


@pytest.mark.asyncio
async def test_group_reader_loads_school_on_get_and_search(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
    group_type_factory: GroupTypeFactory,
) -> None:
    workgroup_type = await group_type_factory(name="workgroup")
    school = await school_factory(name="alpha")
    group = await group_factory(name="group-a", school=school, group_type=workgroup_type)
    reader = SQLAlchemyGroupReader(db_session)

    fetched = await reader.get(group.public_id, load=LoadSpec.from_attributes("school"))
    assert not isinstance(fetched.school, UnloadedType)
    assert fetched.school.name == "alpha"

    searched = list(
        await reader.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value="group-a")),
            load=LoadSpec.from_attributes("school"),
        )
    )
    assert len(searched) == 1
    assert not isinstance(searched[0].school, UnloadedType)
    assert searched[0].school.name == "alpha"


@pytest.mark.asyncio
async def test_user_reader_supports_load_and_search(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    user_factory: UserFactory,
    school_membership_factory: SchoolMembershipFactory,
) -> None:
    school = await school_factory(name="beta")
    user = await user_factory(name="anna", birthday=date(2010, 1, 1))
    await school_membership_factory(user=user, school=school, is_primary=True)

    reader = SQLAlchemyUserReader(db_session)
    results = list(
        await reader.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value="anna")),
            load=LoadSpec.from_attributes("primary_school"),
        )
    )
    assert len(results) == 1
    assert results[0].name == "anna"
    assert not isinstance(results[0].primary_school, UnloadedType)
    assert results[0].primary_school is not None
    assert results[0].primary_school.name == "beta"
    assert isinstance(results[0].legal_wards, UnloadedType)
    assert isinstance(results[0].legal_guardians, UnloadedType)
