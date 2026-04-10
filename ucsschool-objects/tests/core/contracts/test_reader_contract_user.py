from datetime import date
from typing import TYPE_CHECKING

import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import SqliteMemoryUserReader
from ucsschool_objects.core.domain import Filter, Operator, SearchQuery

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from tests.test_types import SchoolFactory, SchoolMembershipFactory, UserFactory


@pytest.mark.asyncio
async def test_user_reader_supports_load_and_search(
    db_session: Session,
    school_factory: SchoolFactory,
    user_factory: UserFactory,
    school_membership_factory: SchoolMembershipFactory,
) -> None:
    school = school_factory(name="beta")
    user = user_factory(name="anna", birthday=date(2010, 1, 1))
    school_membership_factory(user=user, school=school, is_primary=True)

    reader = SqliteMemoryUserReader(db_session)
    results = await reader.search(SearchQuery(where=Filter(field="name", op=Operator.EQ, value="anna")))
    assert len(results) == 1
    assert results[0].name == "anna"
