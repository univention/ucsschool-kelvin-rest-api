import pytest

from ucsschool.kelvin.corelib.adapters.sqlite_memory.readers import SqliteMemorySchoolReader
from ucsschool.kelvin.corelib.domain import Filter, InvalidFilter, Operator, SearchQuery, SortSpec


@pytest.mark.asyncio
async def test_invalid_filter_field_raises_domain_error(db_session, school_factory) -> None:
    school_factory(name="school-a")
    reader = SqliteMemorySchoolReader(db_session)

    with pytest.raises(InvalidFilter, match="Unsupported field"):
        await reader.search(SearchQuery(where=Filter(field="unknown", op=Operator.EQ, value="x")))


@pytest.mark.asyncio
async def test_invalid_sort_field_raises_domain_error(db_session, school_factory) -> None:
    school_factory(name="school-a")
    reader = SqliteMemorySchoolReader(db_session)

    with pytest.raises(InvalidFilter, match="Unsupported sort field"):
        await reader.search(sort_by=(SortSpec(field="invalid", ascending=True),))
