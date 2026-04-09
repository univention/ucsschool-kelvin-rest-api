from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import (
    SqliteMemorySchoolReader,
    SqliteMemoryUserReader,
)
from ucsschool_objects.core.domain import (
    Filter,
    InvalidInFilter,
    InvalidLikeFilter,
    InvalidRangeFilter,
    Operator,
    SearchQuery,
    SortSpec,
    UnsupportedFilterField,
    UnsupportedSortField,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from tests.test_types import SchoolFactory, UserFactory


@pytest.mark.asyncio
async def test_invalid_filter_field_raises_domain_error(
    db_session: Session, school_factory: SchoolFactory
) -> None:
    school_factory(name="school-a")
    reader = SqliteMemorySchoolReader(db_session)
    invalid_filter = Filter(field="unknown", op=Operator.EQ, value="x")

    with pytest.raises(UnsupportedFilterField, match="Unsupported field") as exc_info:
        await reader.search(SearchQuery(where=invalid_filter))
    assert exc_info.value.field == "unknown"


@pytest.mark.asyncio
async def test_invalid_sort_field_raises_domain_error(
    db_session: Session, school_factory: SchoolFactory
) -> None:
    school_factory(name="school-a")
    reader = SqliteMemorySchoolReader(db_session)
    invalid_sort = SortSpec(field="invalid", ascending=True)

    with pytest.raises(UnsupportedSortField, match="Unsupported sort field") as exc_info:
        await reader.search(sort_by=(invalid_sort,))
    assert exc_info.value.field == "invalid"


@pytest.mark.asyncio
async def test_range_filter_with_none_raises_domain_error(
    db_session: Session, user_factory: UserFactory
) -> None:
    user_factory(name="user-a", birthday=date(2010, 1, 1))
    reader = SqliteMemoryUserReader(db_session)
    invalid_filter = Filter(field="birthday", op=Operator.GTE, value=None)

    with pytest.raises(
        InvalidRangeFilter, match="requires a numeric or date-like field and non-null value"
    ) as exc_info:
        await reader.search(SearchQuery(where=invalid_filter))
    assert exc_info.value.field == "birthday"
    assert exc_info.value.operator is Operator.GTE
    assert exc_info.value.value is None


@pytest.mark.asyncio
async def test_range_filter_on_non_range_field_raises_domain_error(
    db_session: Session, user_factory: UserFactory
) -> None:
    user_factory(name="user-a")
    reader = SqliteMemoryUserReader(db_session)
    invalid_filter = Filter(field="name", op=Operator.GTE, value="m")

    with pytest.raises(
        InvalidRangeFilter, match="requires a numeric or date-like field and non-null value"
    ) as exc_info:
        await reader.search(SearchQuery(where=invalid_filter))
    assert exc_info.value.field == "name"
    assert exc_info.value.operator is Operator.GTE
    assert exc_info.value.value == "m"


@pytest.mark.asyncio
async def test_in_filter_with_non_iterable_raises_domain_error(
    db_session: Session, school_factory: SchoolFactory
) -> None:
    school_factory(name="school-a")
    reader = SqliteMemorySchoolReader(db_session)
    invalid_filter = Filter(field="name", op=Operator.IN, value=123)

    with pytest.raises(InvalidInFilter, match="IN operator requires an iterable value") as exc_info:
        await reader.search(SearchQuery(where=invalid_filter))
    assert exc_info.value.field == "name"
    assert exc_info.value.value == 123


@pytest.mark.asyncio
async def test_like_filter_with_non_string_raises_domain_error(
    db_session: Session, school_factory: SchoolFactory
) -> None:
    school_factory(name="school-a")
    reader = SqliteMemorySchoolReader(db_session)
    invalid_filter = Filter(field="name", op=Operator.LIKE, value=123)

    with pytest.raises(InvalidLikeFilter, match="LIKE operator requires a string value") as exc_info:
        await reader.search(SearchQuery(where=invalid_filter))
    assert exc_info.value.field == "name"
    assert exc_info.value.value == 123
