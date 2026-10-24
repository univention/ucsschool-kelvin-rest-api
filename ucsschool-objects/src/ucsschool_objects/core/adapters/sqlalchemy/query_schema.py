# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias, cast

from sqlalchemy import inspect
from sqlalchemy.orm import Mapper
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from ucsschool_objects.database_models import Base

ModelClass: TypeAlias = type[Base]
FieldColumn: TypeAlias = InstrumentedAttribute[object] | ColumnElement[object]


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
        to_many: Whether one root row can relate to many target rows. Such relations
            cannot be sorted on.
    """

    relation_name: str
    target_model: ModelClass
    join_path: tuple[ModelClass, ...]
    join_type: JoinType = JoinType.LEFT_OUTER
    exposed_fields: frozenset[str] = frozenset()
    to_many: bool = True


@dataclass(frozen=True)
class ComputedField:
    roots: tuple[str, ...]
    build: Callable[[Mapping[str, ModelClass]], FieldColumn]


def get_exposed_fields(model: type) -> frozenset[str]:
    """Extract queryable first-level column names from a SQLAlchemy model.

    Only includes actual database columns, skipping relationships and other attributes.
    """
    mapper: Mapper[Base] | None = inspect(model, raiseerr=False)
    if mapper is None:  # pyright: ignore[reportUnnecessaryComparison]
        return frozenset()  # pyright: ignore[reportUnreachable]
    return frozenset(column.key for column in mapper.column_attrs)


def compose_field_map(
    base_field_map: dict[str, FieldColumn],
    nested_field_registry: dict[str, JoinSpec],
) -> dict[str, FieldColumn]:
    """Build a field map from base fields and nested registry dot-path fields."""
    field_map = dict(base_field_map)
    for relation_name, spec in nested_field_registry.items():
        mapper = inspect(spec.target_model)
        target_columns: dict[str, FieldColumn] = {
            column.key: cast(FieldColumn, column.class_attribute) for column in mapper.column_attrs
        }
        for field_name in spec.exposed_fields:
            nested_field_key = f"{relation_name}.{field_name}"
            if field_name in target_columns:
                field_map[nested_field_key] = target_columns[field_name]
    return field_map
