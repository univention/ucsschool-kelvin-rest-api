from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import SqliteMemoryUserReader
from ucsschool_objects.core.domain import Filter, Not, Operator, SearchQuery

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.test_types import AsyncUserFactory as UserFactory


@pytest.mark.asyncio
async def test_negation_filters(db_session: AsyncSession, user_factory: UserFactory) -> None:
    await user_factory(name="active", active=True)
    await user_factory(name="inactive", active=False)
    reader = SqliteMemoryUserReader(db_session)

    q = SearchQuery(where=Not(clause=Filter(field="active", op=Operator.EQ, value=True)))
    results = await reader.search(q)
    assert [item.name for item in results] == ["inactive"]
