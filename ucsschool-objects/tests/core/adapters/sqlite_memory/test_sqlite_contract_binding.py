from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import SqliteMemorySchoolReader

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from tests.test_types import SchoolFactory


@pytest.mark.asyncio
async def test_sqlite_reader_binding_works_with_session(
    db_session: Session, school_factory: SchoolFactory
) -> None:
    school = school_factory(name="binding-sqlite")
    reader = SqliteMemorySchoolReader(db_session)

    fetched = await reader.get(school.public_id)
    assert fetched.name == "binding-sqlite"
