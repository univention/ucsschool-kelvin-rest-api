from datetime import date
from typing import TYPE_CHECKING

import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import (
    SqliteMemorySchoolReader,
    SqliteMemoryUserReader,
)
from ucsschool_objects.core.domain import Filter, InvalidFilter, Operator, SearchQuery, SortSpec

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from tests.test_types import SchoolFactory, UserFactory


@pytest.mark.asyncio
async def test_invalid_filter_field_raises_domain_error(
    db_session: Session, school_factory: SchoolFactory
) -> None:
    school_factory(name="school-a")
    reader = SqliteMemorySchoolReader(db_session)

    with pytest.raises(InvalidFilter, match="Unsupported field"):
        await reader.search(SearchQuery(where=Filter(field="unknown", op=Operator.EQ, value="x")))


@pytest.mark.asyncio
async def test_invalid_sort_field_raises_domain_error(
    db_session: Session, school_factory: SchoolFactory
) -> None:
    school_factory(name="school-a")
    reader = SqliteMemorySchoolReader(db_session)

    with pytest.raises(InvalidFilter, match="Unsupported sort field"):
        await reader.search(sort_by=(SortSpec(field="invalid", ascending=True),))


@pytest.mark.asyncio
async def test_range_filter_with_none_raises_domain_error(
    db_session: Session, user_factory: UserFactory
) -> None:
    user_factory(name="user-a", birthday=date(2010, 1, 1))
    reader = SqliteMemoryUserReader(db_session)

    with pytest.raises(InvalidFilter, match="requires a numeric or date-like field and non-null value"):
        await reader.search(SearchQuery(where=Filter(field="birthday", op=Operator.GTE, value=None)))


@pytest.mark.asyncio
async def test_range_filter_on_non_range_field_raises_domain_error(
    db_session: Session, user_factory: UserFactory
) -> None:
    user_factory(name="user-a")
    reader = SqliteMemoryUserReader(db_session)

    with pytest.raises(InvalidFilter, match="requires a numeric or date-like field and non-null value"):
        await reader.search(SearchQuery(where=Filter(field="name", op=Operator.GTE, value="m")))
