import pytest

from ucsschool.kelvin.corelib.adapters.sqlite_memory.readers import SqliteMemorySchoolReader


@pytest.mark.asyncio
async def test_sqlite_reader_binding_works_with_session(db_session, school_factory) -> None:
    school = school_factory(name="binding-sqlite")
    reader = SqliteMemorySchoolReader(db_session)

    fetched = await reader.get(school.public_id)
    assert fetched is not None
    assert fetched.name == "binding-sqlite"
