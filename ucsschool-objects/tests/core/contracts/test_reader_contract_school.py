from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import SqliteMemorySchoolReader
from ucsschool_objects.core.domain import Filter, Operator, SearchQuery

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from tests.test_types import SchoolFactory


@pytest.mark.asyncio
async def test_school_reader_get_and_search(db_session: Session, school_factory: SchoolFactory) -> None:
    school = school_factory(name="school-1")
    reader = SqliteMemorySchoolReader(db_session)

    fetched = await reader.get(school.public_id)
    assert fetched.name == "school-1"

    results = list(
        await reader.search(SearchQuery(where=Filter(field="name", op=Operator.EQ, value="school-1")))
    )
    assert len(results) == 1
    assert results[0].public_id == school.public_id
