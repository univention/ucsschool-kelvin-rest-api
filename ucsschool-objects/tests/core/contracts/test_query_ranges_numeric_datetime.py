from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import SqliteMemoryUserReader
from ucsschool_objects.core.domain import Filter, Operator, SearchQuery

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.test_types import AsyncUserFactory as UserFactory


@pytest.mark.asyncio
async def test_datetime_range_filters(db_session: AsyncSession, user_factory: UserFactory) -> None:
    await user_factory(name="old", birthday=date(2000, 1, 1))
    await user_factory(name="young", birthday=date(2015, 1, 1))
    reader = SqliteMemoryUserReader(db_session)

    q = SearchQuery(where=Filter(field="birthday", op=Operator.GTE, value=date(2010, 1, 1)))
    results = await reader.search(q)
    assert [item.name for item in results] == ["young"]
