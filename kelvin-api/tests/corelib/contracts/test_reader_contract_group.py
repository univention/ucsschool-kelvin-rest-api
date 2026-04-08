import pytest

from ucsschool.kelvin.corelib.adapters.sqlite_memory.readers import SqliteMemoryGroupReader
from ucsschool.kelvin.corelib.domain import Filter, Operator, SearchQuery, SortSpec


@pytest.mark.asyncio
async def test_group_reader_get_and_search(db_session, group_factory) -> None:
    group = group_factory(name="admins")
    reader = SqliteMemoryGroupReader(db_session)

    fetched = await reader.get(group.public_id)
    assert fetched is not None
    assert fetched.name == "admins"

    results = await reader.search(
        SearchQuery(where=Filter(field="name", op=Operator.EQ, value="admins"))
    )
    assert len(results) == 1
    assert results[0].public_id == group.public_id


@pytest.mark.asyncio
async def test_group_reader_supports_sorting_by_school_fields(
    db_session, school_factory, group_factory
) -> None:
    school_a = school_factory(name="alpha")
    school_b = school_factory(name="beta")
    group_factory(name="group-b", school=school_b)
    group_factory(name="group-a", school=school_a)
    reader = SqliteMemoryGroupReader(db_session)

    results = await reader.search(sort_by=(SortSpec(field="school_name", ascending=True),))
    assert [item.name for item in results] == ["group-a", "group-b"]
