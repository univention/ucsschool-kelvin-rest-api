from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import TypeAlias, cast
from uuid import UUID

from ucsschool_objects.core.domain.models import UnloadedType, UnsetType, domain_asdict

PatchDict: TypeAlias = dict[str, object]
_UNLOADED_MARKER = {"__sentinel__": "UNLOADED"}
_UNSET_MARKER = {"__sentinel__": "UNSET"}


def normalise(obj: object) -> object:
    # asdict leaves set/frozenset, UUID, and date as Python objects; convert them to
    # JSON-serialisable types and sort collections so diffing is deterministic.
    # Dict keys are also normalised so UUID-keyed dicts (e.g. school_memberships)
    # serialise correctly.
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


def to_json(obj: object) -> PatchDict:
    return cast(PatchDict, normalise(domain_asdict(obj)))
