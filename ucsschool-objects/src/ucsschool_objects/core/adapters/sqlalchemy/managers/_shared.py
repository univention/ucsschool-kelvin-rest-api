from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, ClassVar, Protocol, TypeAlias, TypeVar, cast
from uuid import UUID, uuid4

from jsonpatch import JsonPatch  # type: ignore[import-untyped]
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from sqlalchemy.orm.attributes import InstrumentedAttribute
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import FieldColumn
from ucsschool_objects.core.domain import (
    And,
    Filter,
    LoadSpec,
    Not,
    NotFound,
    Or,
    UnloadedType,
)
from ucsschool_objects.core.domain.patch import normalise
from ucsschool_objects.core.domain.ports.manager import JSONPathOperation
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
    "_check_value_presence",
    "generate_public_id",
    "_extract_public_ids",
    "_apply_patch",
    "DataclassInstance",
    "_sync_collection",
    "_sync_scalar_relation",
]

QueryExpr: TypeAlias = Filter | And | Or | Not
ModelClass: TypeAlias = type[Base]
TSelect = TypeVar("TSelect", bound=Select[Any])
TRequired = TypeVar("TRequired")
TModel = TypeVar("TModel", bound=Base)


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


class DataclassInstance(Protocol):
    """Protocol for types decorated with @dataclass."""

    __dataclass_fields__: ClassVar[dict[str, Any]]


def generate_public_id() -> UUID:
    """Generate a new UUID (version 4) for public_id."""
    return uuid4()


def _extract_public_ids(items: list[object]) -> set[UUID]:
    """Extract public_id UUIDs from a list of objects or dicts."""
    ids: set[UUID] = set()
    for item in items:
        if isinstance(item, dict):
            raw = cast(object, item.get("public_id"))
        else:
            raw = getattr(item, "public_id", None)
        if raw is not None:
            ids.add(UUID(str(raw)))
    return ids


def _apply_patch(
    *,
    operations: Sequence[JSONPathOperation],
    current_domain_obj: DataclassInstance,
) -> dict[str, object]:
    """Apply JSON Patch operations to a domain object and return the patched dict."""
    current_dict = cast(dict[str, object], normalise(asdict(current_domain_obj)))
    return cast(dict[str, object], JsonPatch(list(operations)).apply(current_dict))


async def _sync_collection(
    session: AsyncSession,
    model: Any,
    relation: str,
    patched_list: list[object],
    current_list: list[object],
    target_model: type[TModel],
) -> None:
    """Sync a collection relationship based on public_id list comparison."""
    current_ids = _extract_public_ids(current_list)
    patched_ids = _extract_public_ids(patched_list)
    if current_ids == patched_ids:
        return

    if patched_ids:
        result = await session.execute(
            select(target_model).where(getattr(target_model, "public_id").in_(patched_ids))
        )
        setattr(model, relation, list(result.scalars()))
    else:
        setattr(model, relation, [])


async def _sync_scalar_relation(
    session: AsyncSession,
    model: Any,
    relation: str,
    patched_val: object,
    current_val: object,
    target_model: type[TModel],
    *,
    mandatory: bool = True,
) -> None:
    """Sync a scalar (to-one) relationship based on public_id comparison."""
    if patched_val == current_val:
        return

    # To domain objects, relations like 'school' are objects, so we extract its public_id.
    # We wrap it in a list to reuse our helper.
    ids = _extract_public_ids([patched_val] if patched_val is not None else [])
    if not ids:
        if mandatory:
            raise ValueError(f"{model.__class__.__name__}.{relation} must not be null.")
        setattr(model, relation, None)
        return

    public_id = next(iter(ids))
    result = await session.execute(
        select(target_model).where(getattr(target_model, "public_id") == public_id)
    )
    setattr(model, relation, result.scalar_one())


async def _fetch_one_by_public_id(
    session: AsyncSession,
    model_class: type[TModel],
    public_id: UUID,
    object_type: str,
) -> TModel:
    """Fetch a single ORM object by public_id. Raises NotFound if absent."""
    result = (
        await session.execute(select(model_class).where(getattr(model_class, "public_id") == public_id))
    ).scalar_one_or_none()
    if result is None:
        raise NotFound(object_type=object_type, public_id=str(public_id))
    return result


async def _fetch_one_by_name(
    session: AsyncSession,
    model_class: type[TModel],
    name_col: InstrumentedAttribute[str],
    name: str,
    object_type: str,
) -> TModel:
    """Fetch a single ORM object by name column. Raises NotFound if absent."""
    result = (await session.execute(select(model_class).where(name_col == name))).scalar_one_or_none()
    if result is None:
        raise NotFound(object_type=object_type, public_id=name)
    return result


async def _bulk_fetch_by_public_id(
    session: AsyncSession,
    model_class: type[TModel],
    public_ids: Sequence[UUID],
    object_type: str,
) -> dict[UUID, TModel]:
    """Fetch multiple ORM objects via a single IN query keyed by public_id.

    Raises NotFound if any requested public_id has no matching row.
    """
    if not public_ids:
        return {}
    unique_ids = list(dict.fromkeys(public_ids))
    results = (
        (
            await session.execute(
                select(model_class).where(getattr(model_class, "public_id").in_(unique_ids))
            )
        )
        .scalars()
        .all()
    )
    by_id: dict[UUID, TModel] = {cast(UUID, getattr(r, "public_id")): r for r in results}
    missing = set(unique_ids) - by_id.keys()
    if missing:
        raise NotFound(object_type=object_type, public_id=str(next(iter(missing))))
    return by_id


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


def _check_value_presence(
    value: TRequired | UnloadedType, *, object_type: str, field_name: str
) -> TRequired:
    if isinstance(value, UnloadedType):
        raise ValueError(f"{object_type}.{field_name} is required.")
    return value


def _check_nullable_value_presence(
    value: TRequired | UnloadedType | None, *, object_type: str, field_name: str
) -> TRequired | None:
    if value is None:
        return None
    return _check_value_presence(value, object_type=object_type, field_name=field_name)
