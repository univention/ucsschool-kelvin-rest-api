# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
#
# pyright: reportUnusedFunction=false
# Private helpers are imported by sibling modules, so they can look unused here.

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Protocol, Self, TypeAlias, TypeVar, cast
from uuid import UUID, uuid4

from jsonpatch import JsonPatch  # type: ignore[import-untyped]
from sqlalchemy import inspect, select
from sqlalchemy.orm import load_only
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.base import ExecutableOption

from ucsschool_objects.core.adapters.sqlalchemy.query_schema import FieldColumn
from ucsschool_objects.core.domain.errors import NotFound
from ucsschool_objects.core.domain.json import PatchDict, to_json
from ucsschool_objects.core.domain.load_spec import LoadSpec
from ucsschool_objects.core.domain.models import (
    DomainObject,
    UnloadedType,
    _require_loaded,  # pyright: ignore[reportPrivateUsage]
)
from ucsschool_objects.database_models import (
    Base,
    Role as RoleModel,
    School as SchoolModel,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from ucsschool_objects.core.domain.models import UnsetType
    from ucsschool_objects.core.domain.ports.manager import JSONPathOperation

TRequired = TypeVar("TRequired")


class SupportsLoadOptions(Protocol):
    def options(self, *options: ExecutableOption) -> Self:  # pragma: no cover
        ...


class PublicIdCarrier(Protocol):
    @property
    def public_id(self) -> UUID | UnsetType:  # pragma: no cover
        ...


TSelect = TypeVar("TSelect", bound=SupportsLoadOptions)
TModel = TypeVar("TModel", bound=Base)
PublicIdCarrierDict: TypeAlias = dict[str, object]
PublicIdInput: TypeAlias = PublicIdCarrier | PublicIdCarrierDict


def generate_public_id() -> UUID:
    """Generate a new UUID (version 4) for public_id."""
    return uuid4()


def extract_public_ids(items: Sequence[PublicIdInput]) -> set[UUID]:
    """Extract public_id UUIDs from a list of objects or dicts."""
    ids: set[UUID] = set()
    for item in items:
        if isinstance(item, dict):
            raw = item.get("public_id")
        else:
            raw = item.public_id
        if raw is not None:
            ids.add(UUID(str(raw)))
    return ids


def apply_patch(
    *,
    operations: Sequence[JSONPathOperation],
    current_domain_obj: DomainObject,
) -> PatchDict:
    """Apply JSON Patch operations to a domain object and return the patched dict."""
    current_dict = to_json(current_domain_obj)
    # NOTE lib jsonpatch is untyped
    return cast(
        PatchDict,
        JsonPatch(list(operations)).apply(current_dict),  # pyright: ignore[reportUnknownMemberType]
    )


def _public_id_column(model_class: type[TModel]) -> InstrumentedAttribute[UUID]:
    mapper = inspect(model_class, raiseerr=False)
    assert mapper is not None, f"Model class {model_class.__name__} is not SQLAlchemy-inspectable."
    return cast(InstrumentedAttribute[UUID], mapper.column_attrs["public_id"].class_attribute)


async def sync_collection(
    session: AsyncSession,
    patched_list: Sequence[PublicIdInput],
    current_list: Sequence[PublicIdInput],
    target_model: type[TModel],
    set_relation: Callable[[list[TModel]], None],
) -> None:
    """Sync a collection relationship based on public_id list comparison.

    Raises NotFound if any requested public_id has no matching row.
    """
    current_ids = extract_public_ids(current_list)
    patched_ids = extract_public_ids(patched_list)
    if current_ids == patched_ids:
        return

    if patched_ids:
        object_type = target_model.__name__
        records = await bulk_fetch_by_public_id(session, target_model, list(patched_ids), object_type)
        set_relation(list(records.values()))
    else:
        set_relation([])


async def sync_scalar_relation(
    session: AsyncSession,
    model_name: str,
    relation: str,
    patched_val: PublicIdInput | None,
    current_val: PublicIdInput | None,
    target_model: type[TModel],
    set_relation: Callable[[TModel | None], None],
    *,
    mandatory: bool = True,
) -> None:
    """Sync a scalar (to-one) relationship based on public_id comparison."""
    if patched_val == current_val:
        return

    # To domain objects, relations like 'school' are objects, so we extract its public_id.
    # We wrap it in a list to reuse our helper.
    ids = extract_public_ids([patched_val] if patched_val is not None else [])
    if not ids:
        if mandatory:
            raise ValueError(f"{model_name}.{relation} must not be null.")
        set_relation(None)
        return

    public_id = next(iter(ids))
    public_id_column = _public_id_column(target_model)
    result = await session.execute(select(target_model).where(public_id_column == public_id))
    set_relation(result.scalar_one())


async def fetch_one_by_public_id(
    session: AsyncSession,
    model_class: type[TModel],
    public_id: UUID,
    object_type: str,
) -> TModel:
    """Fetch a single ORM object by public_id. Raises NotFound if absent."""
    public_id_column = _public_id_column(model_class)
    result = (
        await session.execute(select(model_class).where(public_id_column == public_id))
    ).scalar_one_or_none()
    if result is None:
        raise NotFound(object_type=object_type, public_id=str(public_id))
    return result


async def bulk_fetch_by_public_id(
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
    public_id_column = _public_id_column(model_class)
    rows = (
        (
            await session.execute(
                select(model_class, public_id_column).where(public_id_column.in_(unique_ids))
            )
        )
        .tuples()
        .all()
    )
    by_id: dict[UUID, TModel] = {public_id: model for model, public_id in rows}
    missing = set(unique_ids) - by_id.keys()
    if missing:
        raise NotFound(object_type=object_type, public_id=str(next(iter(missing))))
    return by_id


def load_requested_scalar_attributes(
    stmt: TSelect,
    public_id_column: InstrumentedAttribute[UUID],
    load: LoadSpec | None,
    attribute_map: dict[str, FieldColumn],
) -> TSelect:
    if load is None:
        return stmt

    requested_columns = [
        cast(InstrumentedAttribute[object], column)
        for name, column in attribute_map.items()
        if load.includes(name)
    ]
    return stmt.options(load_only(public_id_column, *requested_columns))


def school_scalar_columns() -> tuple[InstrumentedAttribute[object], ...]:
    return (
        SchoolModel.record_uid,
        SchoolModel.source_uid,
        SchoolModel.name,
        SchoolModel.display_name,
        SchoolModel.educational_servers,
        SchoolModel.administrative_servers,
        SchoolModel.class_share_file_server,
        SchoolModel.home_share_file_server,
        SchoolModel.udm_properties,
    )


def role_scalar_columns() -> tuple[InstrumentedAttribute[object], ...]:
    return (RoleModel.name, RoleModel.display_name)


def check_nullable_value_presence(
    value: TRequired | UnloadedType | None, *, object_type: str, field_name: str
) -> TRequired | None:
    if value is None:
        return None
    return _require_loaded(value, object_type=object_type, field_name=field_name)
