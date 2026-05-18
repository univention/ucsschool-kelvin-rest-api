import copy
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Generic, Self, TypeVar, cast
from uuid import UUID

from jsonpatch import JsonPatch  # type: ignore[import-untyped]
from ucsschool_objects.core.domain.models import (
    Group,
    School,
    UnloadedType,
    UnsetType,
    User,
    domain_asdict,
)
from ucsschool_objects.core.domain.ports.manager import JSONPathOperation

_T = TypeVar("_T", School, Group, User)

_EMPTY_FROZENSET: frozenset[str] = frozenset()
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
        d = cast(dict[object, object], obj)
        return {normalise(k): normalise(v) for k, v in d.items()}
    if isinstance(obj, (list, set, frozenset)):
        return sorted((normalise(item) for item in cast(Iterable[object], obj)), key=str)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def _patch_ops(
    src_dict: dict[str, object],
    dst_dict: dict[str, object],
    replace_fields: frozenset[str] = _EMPTY_FROZENSET,
) -> Sequence[JSONPathOperation]:
    operations: list[dict[str, object]] = []
    for field in replace_fields:
        src_val = src_dict.pop(field, None)
        dst_val = dst_dict.pop(field, None)
        if src_val != dst_val:
            operations.append({"op": "replace", "path": f"/{field}", "value": dst_val})
    # NOTE lib jsonpatch is untyped
    operations.extend(
        JsonPatch.from_diff(src_dict, dst_dict).patch  # pyright: ignore[reportUnknownMemberType]
    )
    return cast(Sequence[JSONPathOperation], JsonPatch(operations).patch)


def _create_patch(
    src: _T, dst: _T, replace_fields: frozenset[str] = _EMPTY_FROZENSET
) -> Sequence[JSONPathOperation]:
    src_dict = cast(dict[str, object], normalise(domain_asdict(src)))
    dst_dict = cast(dict[str, object], normalise(domain_asdict(dst)))
    return _patch_ops(src_dict, dst_dict, replace_fields)


def create_school_patch(
    src: School, dst: School, replace_fields: frozenset[str] = _EMPTY_FROZENSET
) -> Sequence[JSONPathOperation]:
    """Return a JSON Patch describing the changes needed to transform src into dst.

    Args:
        src: The school in its current state (the baseline).
        dst: The school in its desired state (the target).
        replace_fields: Field names whose collection value should be replaced atomically
            rather than diffed element-wise. Use this when the intent is to overwrite
            the whole collection, not add or remove individual members.
    """
    return _create_patch(src, dst, replace_fields)


def create_group_patch(
    src: Group, dst: Group, replace_fields: frozenset[str] = _EMPTY_FROZENSET
) -> Sequence[JSONPathOperation]:
    """Return a JSON Patch describing the changes needed to transform src into dst.

    Args:
        src: The group in its current state (the baseline).
        dst: The group in its desired state (the target).
        replace_fields: Field names whose collection value should be replaced atomically
            rather than diffed element-wise. Use this when the intent is to overwrite
            the whole collection, not add or remove individual members.
    """
    return _create_patch(src, dst, replace_fields)


def create_user_patch(
    src: User, dst: User, replace_fields: frozenset[str] = _EMPTY_FROZENSET
) -> Sequence[JSONPathOperation]:
    """Return a JSON Patch describing the changes needed to transform src into dst.

    Args:
        src: The user in its current state (the baseline).
        dst: The user in its desired state (the target).
        replace_fields: Field names whose collection value should be replaced atomically
            rather than diffed element-wise. Use this when the intent is to overwrite
            the whole collection, not add or remove individual members.
    """
    return _create_patch(src, dst, replace_fields)


class track_changes(Generic[_T]):
    """Context manager that records all attribute changes made to an object.

    On exit the accumulated changes are available as a JSON Patch via the
    ``patch`` attribute. Dispatches to the appropriate ``create_*_patch``
    function so that any type-specific logic is applied automatically.

    Example::

        with track_changes(school, replace_fields=frozenset({"educational_servers"})) as tracker:
            school.name = "new-name"
            school.educational_servers = {"server1"}

        manager.apply(tracker.patch)

    Args:
        obj: The object to track. It is mutated in place inside the block.
        replace_fields: Passed through to the patch builder — see
            ``create_school_patch`` for semantics.
    """

    def __init__(self, obj: _T, replace_fields: frozenset[str] = _EMPTY_FROZENSET) -> None:
        self._obj: _T = obj
        self._original: _T = obj
        self._replace_fields = replace_fields
        self.patch: Sequence[JSONPathOperation] | None = None

    def __enter__(self) -> Self:
        self._original = copy.copy(self._obj)
        return self

    def __exit__(self, *_: object) -> None:
        if isinstance(self._obj, School) and isinstance(self._original, School):
            self.patch = create_school_patch(self._original, self._obj, self._replace_fields)
        elif isinstance(self._obj, Group) and isinstance(self._original, Group):
            self.patch = create_group_patch(self._original, self._obj, self._replace_fields)
        # pragma: no cover — unreachable: _T is constrained to School | Group | User
        elif isinstance(self._obj, User) and isinstance(self._original, User):  # pragma: no cover
            self.patch = create_user_patch(self._original, self._obj, self._replace_fields)
