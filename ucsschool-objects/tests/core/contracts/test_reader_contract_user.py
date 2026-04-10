from datetime import date

import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import SqliteMemoryUserReader
from ucsschool_objects.core.domain import Filter, Operator, SearchQuery


@pytest.mark.asyncio
async def test_user_reader_supports_load_and_search(
    db_session, school_factory, user_factory, school_membership_factory
) -> None:
    school = school_factory(name="beta")
    user = user_factory(name="anna", birthday=date(2010, 1, 1))
    school_membership_factory(user=user, school=school, is_primary=True)

    reader = SqliteMemoryUserReader(db_session)
    results = await reader.search(SearchQuery(where=Filter(field="name", op=Operator.EQ, value="anna")))
    assert len(results) == 1
    assert results[0].name == "anna"
