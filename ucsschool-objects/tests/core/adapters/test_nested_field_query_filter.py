"""Tests for nested field detection and join injection in query_filter module."""
from __future__ import annotations

from collections.abc import Iterator, Mapping as MappingABC
from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import select
from ucsschool_objects.core.adapters.sqlalchemy.managers import JoinSpec, JoinType
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import (
    _get_filter_column,
    _get_required_joins,
    apply_nested_joins,
)
from ucsschool_objects.core.domain import (
    And,
    Filter,
    Operator,
    SortSpec,
    UnsupportedNestedField,
)
from ucsschool_objects.database_models import (
    Base,
    Group as GroupModel,
    Role as RoleModel,
    SchoolMembership,
    User as UserModel,
)

if TYPE_CHECKING:
    from ucsschool_objects.core.adapters.sqlalchemy.query_filter import FieldColumn


def _r(*names: str) -> dict[str, JoinSpec]:
    """Create a stub registry dict for testing (values are not used by _get_required_joins)."""
    return cast("dict[str, JoinSpec]", {name: None for name in names})


def test_get_required_joins_detects_single_nested_field() -> None:
    """Test that single nested field is detected."""
    filter_expr = Filter("groups.public_id", Operator.EQ, "test-id")
    joins = _get_required_joins(filter_expr, registry=_r("groups"))

    assert "groups" in joins
    assert len(joins) == 1


def test_get_required_joins_detects_multiple_nested_fields() -> None:
    """Test that multiple different nested fields are detected."""
    filter_expr = And(
        (
            Filter("groups.public_id", Operator.EQ, "group-id"),
            Filter("schools.name", Operator.LIKE, "test%"),
        )
    )
    joins = _get_required_joins(filter_expr, registry=_r("groups", "schools", "roles"))

    assert "groups" in joins
    assert "schools" in joins
    assert "roles" not in joins
    assert len(joins) == 2


def test_get_required_joins_ignores_scalar_fields() -> None:
    """Test that scalar fields don't trigger joins."""
    filter_expr = Filter("name", Operator.LIKE, "test")
    joins = _get_required_joins(filter_expr, registry=_r("groups"))

    assert len(joins) == 0


def test_get_required_joins_from_sort_specs() -> None:
    """Test that required joins are detected from sort specs."""
    sort_by = [
        SortSpec("groups.name", ascending=True),
        SortSpec("public_id", ascending=False),
    ]
    joins = _get_required_joins(sort_by, registry=_r("groups"))

    assert "groups" in joins
    assert len(joins) == 1


def test_get_required_joins_with_no_registry() -> None:
    """Test that no joins are required when registry is None."""
    filter_expr = Filter("groups.public_id", Operator.EQ, "test-id")
    joins = _get_required_joins(filter_expr, registry=None)

    assert len(joins) == 0


def test_get_required_joins_with_empty_registry() -> None:
    """Test that no joins are required when registry is empty."""
    filter_expr = Filter("groups.public_id", Operator.EQ, "test-id")
    joins = _get_required_joins(filter_expr, registry={})

    assert len(joins) == 0

    # Also cover the None-expression fallback path with a non-empty registry.
    joins_none_expr = _get_required_joins(None, registry=_r("groups"))
    assert len(joins_none_expr) == 0


def test_get_required_joins_ignores_unknown_relations() -> None:
    """Test that unknown relations in queries are ignored (will error later in validation)."""
    filter_expr = Filter("unknown_relation.field", Operator.EQ, "test")
    joins = _get_required_joins(filter_expr, registry=_r("groups"))

    # unknown_relation not in registry, so no join is added
    # (validation error will occur later)
    assert len(joins) == 0


def test_get_required_joins_deduplicates() -> None:
    """Test that the same relationship appearing multiple times results in single join."""
    filter_expr = And(
        (
            Filter("groups.public_id", Operator.EQ, "group1"),
            Filter("groups.name", Operator.LIKE, "test%"),
        )
    )
    joins = _get_required_joins(filter_expr, registry=_r("groups"))

    assert "groups" in joins
    assert len(joins) == 1


@pytest.mark.asyncio
async def test_apply_nested_joins_applies_left_outer_by_default() -> None:
    """Test that apply_nested_joins applies left outer joins and DISTINCT."""
    registry = {
        "groups": JoinSpec(
            relation_name="groups",
            target_model=GroupModel,
            join_path=(SchoolMembership, GroupModel),
            join_type=JoinType.LEFT_OUTER,
            exposed_fields=frozenset(["public_id", "name"]),
        ),
    }

    stmt = select(UserModel)
    joined_stmt = apply_nested_joins(stmt, {"groups"}, registry)

    # Single nested N:M join paths can duplicate root rows; DISTINCT must be applied.
    assert joined_stmt._distinct is True
    assert joined_stmt is not None


@pytest.mark.asyncio
async def test_apply_nested_joins_applies_distinct_for_multiple_joins() -> None:
    """Test that DISTINCT is applied when multiple joins are present."""
    registry = {
        "groups": JoinSpec(
            relation_name="groups",
            target_model=GroupModel,
            join_path=(SchoolMembership, GroupModel),
            join_type=JoinType.LEFT_OUTER,
            exposed_fields=frozenset(["public_id"]),
        ),
        "roles": JoinSpec(
            relation_name="roles",
            target_model=RoleModel,
            join_path=(SchoolMembership, RoleModel),
            join_type=JoinType.LEFT_OUTER,
            exposed_fields=frozenset(["public_id"]),
        ),
    }

    stmt = select(UserModel)
    joined_stmt = apply_nested_joins(stmt, {"groups", "roles"}, registry)

    assert joined_stmt._distinct is True
    assert joined_stmt is not None


@pytest.mark.asyncio
async def test_apply_nested_joins_with_empty_registry_returns_unchanged() -> None:
    """Test that no joins are applied when registry is None or empty."""
    stmt = select(UserModel)
    result = apply_nested_joins(stmt, set(), None)

    assert result == stmt

    result2 = apply_nested_joins(stmt, {"groups"}, {})
    assert result2 == stmt


def test_unsupported_nested_field_error_message_includes_allowed_relations() -> None:
    """Test that UnsupportedNestedField error includes allowed relations."""
    error = UnsupportedNestedField(
        nested_field="unknown.field",
        root_relation="unknown",
        allowed_relations=["groups", "roles", "schools"],
    )

    msg = str(error)
    assert "unknown" in msg
    assert "groups" in msg


def test_unsupported_nested_field_error_message_includes_supported_fields() -> None:
    """Test that UnsupportedNestedField error includes supported fields."""
    error = UnsupportedNestedField(
        nested_field="groups.bad_field",
        reason="Field 'bad_field' not supported on relation 'groups'",
        supported_fields=["public_id", "name", "email"],
    )

    msg = str(error)
    assert "bad_field" in msg
    assert "public_id" in msg
    assert "name" in msg


def test_get_filter_column_resolves_nested_field_without_field_map_entry() -> None:
    """_get_filter_column resolves a valid nested field even when not pre-populated in field_map."""
    filter_expr = Filter("groups.public_id", Operator.EQ, "test-id")
    # field_map contains only scalar fields — nested key deliberately absent
    field_map = {"public_id": UserModel.public_id, "name": UserModel.name}
    registry = {
        "groups": JoinSpec(
            relation_name="groups",
            target_model=GroupModel,
            join_path=(SchoolMembership, GroupModel),
            join_type=JoinType.LEFT_OUTER,
            exposed_fields=frozenset(["public_id", "name"]),
        ),
    }

    column = _get_filter_column(filter_expr, field_map, registry)
    assert column is GroupModel.public_id


def test_get_filter_column_raises_when_exposed_field_has_no_mapped_column() -> None:
    """_get_filter_column raises UnsupportedNestedField when the field is in exposed_fields but
    has no corresponding mapped column attribute on the target model."""
    filter_expr = Filter("groups.nonexistent_attr", Operator.EQ, "value")
    field_map = {"public_id": UserModel.public_id}
    registry = {
        "groups": JoinSpec(
            relation_name="groups",
            target_model=GroupModel,
            join_path=(SchoolMembership, GroupModel),
            join_type=JoinType.LEFT_OUTER,
            # Declare the field as exposed even though it has no mapped column on GroupModel.
            exposed_fields=frozenset(["nonexistent_attr"]),
        ),
    }

    with pytest.raises(UnsupportedNestedField):
        _get_filter_column(filter_expr, field_map, registry)


def test_get_filter_column_returns_column_from_field_map_via_get() -> None:
    """_get_filter_column returns the column from field_map.get() (line 209) when the dotted
    key is present in the mapping but hidden from __contains__, bypassing the fast-path."""

    class _HideDottedKeys(MappingABC[str, "FieldColumn"]):
        """A Mapping whose __contains__ never reports dotted keys, forcing the nested branch."""

        def __init__(self, data: dict[str, FieldColumn]) -> None:
            self._data = data

        def __getitem__(self, key: str) -> FieldColumn:
            return self._data[key]

        def __iter__(self) -> Iterator[str]:
            return iter(self._data)

        def __len__(self) -> int:
            return len(self._data)

        def __contains__(self, key: object) -> bool:
            if isinstance(key, str) and "." in key:
                return False
            return key in self._data

    filter_expr = Filter("groups.public_id", Operator.EQ, "test-id")
    field_map: MappingABC[str, FieldColumn] = _HideDottedKeys(
        {
            "public_id": UserModel.public_id,
            "groups.public_id": GroupModel.public_id,
        }
    )
    registry = {
        "groups": JoinSpec(
            relation_name="groups",
            target_model=GroupModel,
            join_path=(SchoolMembership, GroupModel),
            join_type=JoinType.LEFT_OUTER,
            exposed_fields=frozenset(["public_id"]),
        ),
    }

    column = _get_filter_column(filter_expr, field_map, registry)
    assert column is GroupModel.public_id


def test_get_filter_column_raises_when_target_model_is_not_mapped() -> None:
    """_get_filter_column raises UnsupportedNestedField when inspect() returns None
    (target_model is not a SQLAlchemy-instrumented class), covering the inspection is None branch."""

    class PlainClass:  # not a SQLAlchemy model
        pass

    filter_expr = Filter("plain.some_field", Operator.EQ, "value")
    field_map = {"public_id": UserModel.public_id}
    registry = {
        "plain": JoinSpec(
            relation_name="plain",
            target_model=cast("type[Base]", PlainClass),
            join_path=(),
            join_type=JoinType.LEFT_OUTER,
            exposed_fields=frozenset(["some_field"]),
        ),
    }

    with pytest.raises(UnsupportedNestedField):
        _get_filter_column(filter_expr, field_map, registry)
