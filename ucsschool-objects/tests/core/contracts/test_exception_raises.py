from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

import pytest
from ucsschool_objects.core.adapters.sqlalchemy import (
    SQLAlchemyGroupManager,
    SQLAlchemyRoleManager,
    SQLAlchemySchoolManager,
    SQLAlchemyUserManager,
)
from ucsschool_objects.core.domain import (
    And,
    EmptyAndClause,
    EmptyOrClause,
    Filter,
    InvalidFilter,
    InvalidInFilter,
    InvalidLikeFilter,
    NotFound,
    Operator,
    Or,
    SearchQuery,
    SortSpec,
    UnsupportedFilterField,
    UnsupportedSortField,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.test_types import (
        AsyncGroupFactory as GroupFactory,
        AsyncGroupTypeFactory as GroupTypeFactory,
    )
    from ucsschool_objects.core.domain.ports.manager import Manager


FieldInvalidFilter = UnsupportedFilterField | UnsupportedSortField | InvalidInFilter | InvalidLikeFilter


def build_exception_case(
    id: str,
    search_args: dict[str, Any],
    expected_exc_type: type[FieldInvalidFilter],
    expected_exc_message: str,
    expected_exc_field: str,
    expected_exc_value: object | None,
) -> Any:
    return pytest.param(
        search_args,
        expected_exc_type,
        expected_exc_message,
        expected_exc_field,
        expected_exc_value,
        id=id,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "search_args, expected_exc_type, expected_exc_message, expected_exc_field, expected_exc_value",
    [
        build_exception_case(
            id="unsupported-filter-field",
            search_args={
                "query": SearchQuery(where=Filter(field="field_name", op=Operator.EQ, value="x"))
            },
            expected_exc_type=UnsupportedFilterField,
            expected_exc_message="Unsupported field",
            expected_exc_field="field_name",
            expected_exc_value=None,
        ),
        build_exception_case(
            id="unsupported-sort-field",
            search_args={"sort_by": (SortSpec(field="nonexistent", ascending=True),)},
            expected_exc_type=UnsupportedSortField,
            expected_exc_message="Unsupported sort field",
            expected_exc_field="nonexistent",
            expected_exc_value=None,
        ),
        build_exception_case(
            id="invalid-in-filter-value",
            search_args={"query": SearchQuery(where=Filter(field="name", op=Operator.IN, value=99))},
            expected_exc_type=InvalidInFilter,
            expected_exc_message="IN operator requires an iterable value",
            expected_exc_field="name",
            expected_exc_value=99,
        ),
        build_exception_case(
            id="invalid-like-filter-value",
            search_args={"query": SearchQuery(where=Filter(field="name", op=Operator.LIKE, value=42))},
            expected_exc_type=InvalidLikeFilter,
            expected_exc_message="LIKE operator requires a string value",
            expected_exc_field="name",
            expected_exc_value=42,
        ),
        build_exception_case(
            id="invalid-ilike-filter-value",
            search_args={"query": SearchQuery(where=Filter(field="name", op=Operator.ILIKE, value=42))},
            expected_exc_type=InvalidLikeFilter,
            expected_exc_message="LIKE operator requires a string value",
            expected_exc_field="name",
            expected_exc_value=42,
        ),
    ],
)
async def test_group_manager_raises_invalid_filter(
    db_session: AsyncSession,
    group_factory: GroupFactory,
    roles_factory: GroupTypeFactory,
    search_args: dict[str, Any],
    expected_exc_type: type[FieldInvalidFilter],
    expected_exc_message: str,
    expected_exc_field: str,
    expected_exc_value: object | None,
) -> None:
    """
    Tests whether SQLAlchemyGroupManager.search raises the concrete InvalidFilter subtype
    for each failure mode.
    """
    school_class_type = await roles_factory(name="school_class")
    await group_factory(roles=school_class_type)
    manager = SQLAlchemyGroupManager(db_session)

    with pytest.raises(expected_exc_type, match=expected_exc_message) as exc_info:
        await manager.search(**search_args)
    error = cast("FieldInvalidFilter", exc_info.value)
    assert error.field == expected_exc_field
    if expected_exc_value is not None:
        assert isinstance(error, (InvalidInFilter, InvalidLikeFilter))
        assert error.value == expected_exc_value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "where_expr, expected_exc_type, expected_reason",
    [
        (And(clauses=()), EmptyAndClause, "AND query requires at least one clause"),
        (Or(clauses=()), EmptyOrClause, "OR query requires at least one clause"),
    ],
)
async def test_empty_logical_clause_raises_invalid_filter(
    db_session: AsyncSession,
    where_expr: And | Or,
    expected_exc_type: type[InvalidFilter],
    expected_reason: str,
) -> None:
    """Tests whether empty And/Or query clauses raise the corresponding dedicated error type."""
    manager = SQLAlchemySchoolManager(db_session)

    with pytest.raises(expected_exc_type, match=expected_reason):
        await manager.search(SearchQuery(where=where_expr))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "manager_cls, object_type",
    [
        (SQLAlchemyGroupManager, "Group"),
        (SQLAlchemyRoleManager, "Role"),
        (SQLAlchemySchoolManager, "School"),
        (SQLAlchemyUserManager, "User"),
    ],
)
async def test_not_found_raised_for_missing_object(
    db_session: AsyncSession,
    manager_cls: Callable[[AsyncSession], Manager[object]],
    object_type: str,
) -> None:
    """
    Tests whether Manager.get raises NotFound with correct object_type and
    public_id for unknown IDs.
    """
    missing_id = uuid.uuid4()
    manager = manager_cls(db_session)

    with pytest.raises(NotFound) as exc_info:
        await manager.get(missing_id)
    assert exc_info.value.object_type == object_type
    assert exc_info.value.public_id == str(missing_id)
    assert object_type in str(exc_info.value)
    assert str(missing_id) in str(exc_info.value)
