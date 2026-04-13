from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import SqliteMemoryGroupReader
from ucsschool_objects.core.domain import Filter, Operator, SearchQuery, SortSpec

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.test_types import AsyncGroupFactory as GroupFactory, AsyncSchoolFactory as SchoolFactory


@pytest.mark.asyncio
async def test_group_reader_get_and_search(
    db_session: AsyncSession, group_factory: GroupFactory
) -> None:
    group = await group_factory(name="admins")
    reader = SqliteMemoryGroupReader(db_session)

    fetched = await reader.get(group.public_id)
    assert fetched.name == "admins"

    results = list(
        await reader.search(SearchQuery(where=Filter(field="name", op=Operator.EQ, value="admins")))
    )
    assert len(results) == 1
    assert results[0].public_id == group.public_id


@pytest.mark.asyncio
async def test_group_reader_supports_sorting_by_school_fields(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
) -> None:
    school_a = await school_factory(name="alpha")
    school_b = await school_factory(name="beta")
    await group_factory(name="group-b", school=school_b)
    await group_factory(name="group-a", school=school_a)
    reader = SqliteMemoryGroupReader(db_session)

    results = list(await reader.search(sort_by=(SortSpec(field="school_name", ascending=True),)))
    assert [item.name for item in results] == ["group-a", "group-b"]
