from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeAlias, TypeVar, cast

from sqlalchemy import Select
from sqlalchemy.orm import load_only
from sqlalchemy.orm.attributes import InstrumentedAttribute
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import FieldColumn
from ucsschool_objects.core.domain import (
    And,
    Filter,
    LoadSpec,
    Not,
    Or,
)
from ucsschool_objects.database_models import (
    Base,
    Role as RoleModel,
    School as SchoolModel,
)

__all__ = [
    "JoinType",
    "JoinSpec",
    "QueryExpr",
    "ModelClass",
    "TSelect",
    "FieldColumn",
]

QueryExpr: TypeAlias = Filter | And | Or | Not
ModelClass: TypeAlias = type[Base]
TSelect = TypeVar("TSelect", bound=Select[Any])


class JoinType(str, Enum):
    LEFT_OUTER = "left_outer"
    INNER = "inner"


@dataclass(frozen=True)
class JoinSpec:
    """Specification for how to join a nested relationship.

    Attributes:
        relation_name: Name of the relationship (e.g., "groups", "school", "roles").
        target_model: The ORM model to join to.
        join_path: Tuple of models to join in order (e.g., (SchoolMembership, GroupModel)).
        join_type: Either "left_outer" (default) for optional relationships or "inner" for required.
        exposed_fields: Frozenset of field names on target_model that are queryable.
    """

    relation_name: str
    target_model: ModelClass
    join_path: tuple[ModelClass, ...]
    join_type: JoinType = JoinType.LEFT_OUTER
    exposed_fields: frozenset[str] = frozenset()


def _get_exposed_fields(model: type) -> frozenset[str]:
    """Extract queryable first-level column names from a SQLAlchemy model.

    Only includes actual database columns, skipping relationships and other attributes.
    """
    fields = set()
    for attr_name in dir(model):
        if attr_name.startswith("_"):
            continue
        try:
            attr = getattr(model, attr_name)
            # Check if it's an InstrumentedAttribute with a columns property
            if isinstance(attr, InstrumentedAttribute):
                if hasattr(attr.property, "columns"):
                    fields.add(attr_name)
        except (AttributeError, TypeError):
            # Skip attributes that can't be accessed or aren't column-backed
            continue
    return frozenset(fields)


def _iter_filters(expr: QueryExpr) -> Iterable[Filter]:
    if isinstance(expr, Filter):
        yield expr
        return
    if isinstance(expr, (And, Or)):
        for clause in expr.clauses:
            yield from _iter_filters(clause)
        return
    yield from _iter_filters(expr.clause)


def _compose_field_map(
    base_field_map: dict[str, FieldColumn],
    nested_field_registry: dict[str, JoinSpec],
) -> dict[str, FieldColumn]:
    """Build a field map from base fields and nested registry dot-path fields."""
    field_map = dict(base_field_map)
    for relation_name, spec in nested_field_registry.items():
        for field_name in spec.exposed_fields:
            nested_field_key = f"{relation_name}.{field_name}"
            field_map[nested_field_key] = getattr(spec.target_model, field_name)
    return field_map


def _load_requested_scalar_attributes(
    stmt: TSelect,
    public_id_column: InstrumentedAttribute[Any],
    load: LoadSpec | None,
    attribute_map: dict[str, FieldColumn],
) -> TSelect:
    if load is None:
        return stmt

    requested_columns = [
        cast(InstrumentedAttribute[Any], column)
        for name, column in attribute_map.items()
        if load.includes(name)
    ]
    return stmt.options(load_only(public_id_column, *requested_columns))


def _school_scalar_columns() -> tuple[InstrumentedAttribute[Any], ...]:
    return (
        SchoolModel.record_uid,
        SchoolModel.source_uid,
        SchoolModel.name,
        SchoolModel.display_name,
        SchoolModel.educational_servers,
        SchoolModel.administrative_servers,
        SchoolModel.class_share_file_server,
        SchoolModel.home_share_file_server,
    )


def _role_scalar_columns() -> tuple[InstrumentedAttribute[Any], ...]:
    return (RoleModel.name, RoleModel.display_name)
