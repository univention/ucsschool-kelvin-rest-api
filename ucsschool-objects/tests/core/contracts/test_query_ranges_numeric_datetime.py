from datetime import date

import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import SqliteMemoryUserReader
from ucsschool_objects.core.domain import Filter, Operator, SearchQuery


@pytest.mark.asyncio
async def test_datetime_range_filters(db_session, user_factory) -> None:
    user_factory(name="old", birthday=date(2000, 1, 1))
    user_factory(name="young", birthday=date(2015, 1, 1))
    reader = SqliteMemoryUserReader(db_session)

    q = SearchQuery(where=Filter(field="birthday", op=Operator.GTE, value=date(2010, 1, 1)))
    results = await reader.search(q)
    assert [item.name for item in results] == ["young"]
