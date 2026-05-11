"""Tests for nested field detection and join injection in query_filter module."""
from __future__ import annotations

from typing import cast

import pytest
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


def _r(*names: str) -> dict[str, JoinSpec]:
    """Create a stub registry dict for testing (values are not used by _get_required_joins)."""
    return cast(dict[str, JoinSpec], {name: None for name in names})


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
    from sqlalchemy import select
    from ucsschool_objects.core.adapters.sqlalchemy.managers import JoinSpec
    from ucsschool_objects.database_models import (
        Group as GroupModel,
        SchoolMembership,
        User as UserModel,
    )

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
    from sqlalchemy import select
    from ucsschool_objects.core.adapters.sqlalchemy.managers import JoinSpec
    from ucsschool_objects.database_models import (
        Group as GroupModel,
        Role as RoleModel,
        SchoolMembership,
        User as UserModel,
    )

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
    from sqlalchemy import select
    from ucsschool_objects.database_models import User as UserModel

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
    from ucsschool_objects.database_models import (
        Group as GroupModel,
        SchoolMembership,
        User as UserModel,
    )

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
