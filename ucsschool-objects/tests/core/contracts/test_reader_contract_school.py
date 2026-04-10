import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import SqliteMemorySchoolReader
from ucsschool_objects.core.domain import Filter, Operator, SearchQuery


@pytest.mark.asyncio
async def test_school_reader_get_and_search(db_session, school_factory) -> None:
    school = school_factory(name="school-1")
    reader = SqliteMemorySchoolReader(db_session)

    fetched = await reader.get(school.public_id)
    assert fetched is not None
    assert fetched.name == "school-1"

    results = await reader.search(
        SearchQuery(where=Filter(field="name", op=Operator.EQ, value="school-1"))
    )
    assert len(results) == 1
    assert results[0].public_id == school.public_id
