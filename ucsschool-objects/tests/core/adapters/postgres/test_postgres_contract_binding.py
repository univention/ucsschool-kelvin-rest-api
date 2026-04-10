from typing import TYPE_CHECKING

import pytest
from ucsschool_objects.core.adapters.postgres.readers import PostgresSchoolReader

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from tests.test_types import SchoolFactory


@pytest.mark.asyncio
async def test_postgres_reader_binding_works_with_session(
    postgres_db_session: Session, school_factory: SchoolFactory
) -> None:
    school = school_factory(name="binding-postgres", db_session=postgres_db_session)
    reader = PostgresSchoolReader(postgres_db_session)

    fetched = await reader.get(school.public_id)
    assert fetched is not None
    assert fetched.name == "binding-postgres"
