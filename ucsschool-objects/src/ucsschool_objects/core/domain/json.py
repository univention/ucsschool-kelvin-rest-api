from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import TypeAlias, cast
from uuid import UUID

from ucsschool_objects.core.domain.models import (
    SerializableDomainObject,
    UnloadedType,
    UnsetType,
    domain_object_properties,
)

PatchDict: TypeAlias = dict[str, object]
_UNLOADED_MARKER = {"__sentinel__": "UNLOADED"}
_UNSET_MARKER = {"__sentinel__": "UNSET"}


def normalise(obj: object) -> object:
    # Convert values to JSON-serialisable types and sort collections so diffing is
    # deterministic. Dict keys are also normalised so UUID-keyed dicts (e.g.
    # school_memberships) serialise correctly.
    if isinstance(obj, UnloadedType):
        return dict(_UNLOADED_MARKER)
    if isinstance(obj, UnsetType):
        return dict(_UNSET_MARKER)
    if isinstance(obj, dict):
        data = cast(dict[object, object], obj)
        return {normalise(key): normalise(value) for key, value in data.items()}
    if isinstance(obj, (list, set, frozenset)):
        return sorted((normalise(item) for item in cast(Iterable[object], obj)), key=str)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def _serialize_value(value: object) -> object:
    if isinstance(value, (UnloadedType, UnsetType)):
        return value

    if isinstance(value, SerializableDomainObject):
        return domain_object_properties(value, _serialize_value)

    if isinstance(value, dict):
        dict_value = cast(dict[object, object], value)
        return {_serialize_value(key): _serialize_value(item) for key, item in dict_value.items()}
    if isinstance(value, list):
        list_value = cast(list[object], value)
        return [_serialize_value(item) for item in list_value]
    if isinstance(value, tuple):
        tuple_value = cast(tuple[object, ...], value)
        return tuple(_serialize_value(item) for item in tuple_value)
    if isinstance(value, set):
        set_value = cast(set[object], value)
        return [_serialize_value(item) for item in set_value]
    if isinstance(value, frozenset):
        frozenset_value = cast(frozenset[object], value)
        return [_serialize_value(item) for item in frozenset_value]

    return value


def to_json(obj: object) -> PatchDict:
    return cast(PatchDict, normalise(_serialize_value(obj)))
