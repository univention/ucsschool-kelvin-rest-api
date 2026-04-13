from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest
from ucsschool_objects.core.adapters.sqlalchemy import (
    SQLAlchemySchoolClassReader,
    SQLAlchemySchoolReader,
    SQLAlchemyUserReader,
    SQLAlchemyWorkGroupReader,
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
        AsyncSchoolFactory as SchoolFactory,
        AsyncSchoolMembershipFactory as SchoolMembershipFactory,
        AsyncUserFactory as UserFactory,
    )


@pytest.mark.asyncio
async def test_school_reader_get_and_search(
    db_session: AsyncSession, school_factory: SchoolFactory
) -> None:
    school = await school_factory(name="school-1")
    reader = SQLAlchemySchoolReader(db_session)

    fetched = await reader.get(school.public_id)
    assert fetched.name == "school-1"

    results = list(
        await reader.search(SearchQuery(where=Filter(field="name", op=Operator.EQ, value="school-1")))
    )
    assert len(results) == 1
    assert results[0].public_id == school.public_id


@pytest.mark.asyncio
async def test_school_class_reader_get_and_search(
    db_session: AsyncSession, group_factory: GroupFactory, group_type_factory: GroupTypeFactory
) -> None:
    school_class_type = await group_type_factory(name="school_class")
    school_class = await group_factory(name="class-a", group_type=school_class_type)
    reader = SQLAlchemySchoolClassReader(db_session)

    fetched = await reader.get(school_class.public_id)
    assert fetched.name == "class-a"

    results = list(
        await reader.search(SearchQuery(where=Filter(field="name", op=Operator.EQ, value="class-a")))
    )
    assert len(results) == 1
    assert results[0].public_id == school_class.public_id


@pytest.mark.asyncio
async def test_workgroup_reader_get_and_search(
    db_session: AsyncSession, group_factory: GroupFactory, group_type_factory: GroupTypeFactory
) -> None:
    workgroup_type = await group_type_factory(name="workgroup")
    workgroup = await group_factory(name="admins", group_type=workgroup_type)
    reader = SQLAlchemyWorkGroupReader(db_session)

    fetched = await reader.get(workgroup.public_id)
    assert fetched.name == "admins"

    results = list(
        await reader.search(SearchQuery(where=Filter(field="name", op=Operator.EQ, value="admins")))
    )
    assert len(results) == 1
    assert results[0].public_id == workgroup.public_id


@pytest.mark.asyncio
async def test_workgroup_reader_supports_sorting_by_school_fields(
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
    reader = SQLAlchemyWorkGroupReader(db_session)

    results = list(await reader.search(sort_by=(SortSpec(field="school_name", ascending=True),)))
    assert [item.name for item in results] == ["group-a", "group-b"]


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
            load=LoadSpec.from_relations("school_memberships"),
        )
    )
    assert len(results) == 1
    assert results[0].name == "anna"
    assert not isinstance(results[0].primary_school, UnloadedType)
    assert results[0].primary_school is not None
    assert results[0].primary_school.name == "beta"
    assert isinstance(results[0].legal_wards, UnloadedType)
    assert isinstance(results[0].legal_guardians, UnloadedType)
