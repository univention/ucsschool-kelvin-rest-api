import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import SqliteMemoryUserReader
from ucsschool_objects.core.domain import Filter, Not, Operator, SearchQuery


@pytest.mark.asyncio
async def test_negation_filters(db_session, user_factory) -> None:
    user_factory(name="active", active=True)
    user_factory(name="inactive", active=False)
    reader = SqliteMemoryUserReader(db_session)

    q = SearchQuery(where=Not(clause=Filter(field="active", op=Operator.EQ, value=True)))
    results = await reader.search(q)
    assert [item.name for item in results] == ["inactive"]
