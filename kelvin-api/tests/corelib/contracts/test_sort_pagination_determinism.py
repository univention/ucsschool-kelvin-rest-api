import pytest

from ucsschool.kelvin.corelib.adapters.sqlite_memory.readers import SqliteMemorySchoolReader
from ucsschool.kelvin.corelib.domain import SortSpec


@pytest.mark.asyncio
async def test_deterministic_sort_and_pagination(db_session, school_factory) -> None:
    school_factory(name="s2")
    school_factory(name="s1")
    school_factory(name="s3")
    reader = SqliteMemorySchoolReader(db_session)

    ordered = await reader.search(sort_by=(SortSpec(field="name", ascending=True),), limit=10, offset=0)
    assert [item.name for item in ordered] == ["s1", "s2", "s3"]

    page = await reader.search(sort_by=(SortSpec(field="name", ascending=True),), limit=2, offset=1)
    assert [item.name for item in page] == ["s2", "s3"]
