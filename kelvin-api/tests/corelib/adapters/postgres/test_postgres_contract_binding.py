import pytest

from ucsschool.kelvin.corelib.adapters.postgres.readers import PostgresSchoolReader


@pytest.mark.asyncio
async def test_postgres_reader_binding_works_with_session(postgres_db_session, school_factory) -> None:
    school = school_factory(name="binding-postgres", db_session=postgres_db_session)
    reader = PostgresSchoolReader(postgres_db_session)

    fetched = await reader.get(school.public_id)
    assert fetched is not None
    assert fetched.name == "binding-postgres"
