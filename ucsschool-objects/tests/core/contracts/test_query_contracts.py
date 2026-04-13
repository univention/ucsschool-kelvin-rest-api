from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from ucsschool_objects.core.adapters.sqlalchemy import (
    SQLAlchemySchoolReader,
    SQLAlchemyUserReader,
)
from ucsschool_objects.core.domain import Filter, Not, Operator, SearchQuery, SortSpec

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.test_types import AsyncSchoolFactory as SchoolFactory, AsyncUserFactory as UserFactory


@pytest.mark.asyncio
async def test_query_negation_filters(db_session: AsyncSession, user_factory: UserFactory) -> None:
    await user_factory(name="active", active=True)
    await user_factory(name="inactive", active=False)
    reader = SQLAlchemyUserReader(db_session)

    q = SearchQuery(where=Not(clause=Filter(field="active", op=Operator.EQ, value=True)))
    results = await reader.search(q)
    assert [item.name for item in results] == ["inactive"]


@pytest.mark.asyncio
async def test_query_datetime_range_filters(db_session: AsyncSession, user_factory: UserFactory) -> None:
    await user_factory(name="old", birthday=date(2000, 1, 1))
    await user_factory(name="young", birthday=date(2015, 1, 1))
    reader = SQLAlchemyUserReader(db_session)

    q = SearchQuery(where=Filter(field="birthday", op=Operator.GTE, value=date(2010, 1, 1)))
    results = await reader.search(q)
    assert [item.name for item in results] == ["young"]


@pytest.mark.asyncio
async def test_query_sort_and_pagination_deterministic(
    db_session: AsyncSession, school_factory: SchoolFactory
) -> None:
    await school_factory(name="s2")
    await school_factory(name="s1")
    await school_factory(name="s3")
    reader = SQLAlchemySchoolReader(db_session)

    ordered = list(
        await reader.search(sort_by=(SortSpec(field="name", ascending=True),), limit=10, offset=0)
    )
    assert [item.name for item in ordered] == ["s1", "s2", "s3"]

    page = list(
        await reader.search(sort_by=(SortSpec(field="name", ascending=True),), limit=2, offset=1)
    )
    assert [item.name for item in page] == ["s2", "s3"]


@pytest.mark.asyncio
async def test_query_sort_and_pagination_with_duplicate_sort_keys(
    db_session: AsyncSession, school_factory: SchoolFactory
) -> None:
    first = await school_factory(
        name="s1",
        class_share_file_server="same-server",
        public_id=UUID("00000000-0000-0000-0000-00000000000a"),
    )
    second = await school_factory(
        name="s2",
        class_share_file_server="same-server",
        public_id=UUID("00000000-0000-0000-0000-00000000000b"),
    )
    await school_factory(name="s3", class_share_file_server="zzz-server")
    reader = SQLAlchemySchoolReader(db_session)
    duplicate_public_ids = [str(first.public_id), str(second.public_id)]

    ordered = list(
        await reader.search(
            sort_by=(SortSpec(field="class_share_file_server", ascending=True),), limit=10, offset=0
        )
    )
    assert [str(item.public_id) for item in ordered[:2]] == duplicate_public_ids

    page = list(
        await reader.search(
            sort_by=(SortSpec(field="class_share_file_server", ascending=True),), limit=1, offset=1
        )
    )
    assert str(page[0].public_id) == duplicate_public_ids[1]
