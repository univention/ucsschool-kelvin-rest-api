import copy
from collections.abc import Sequence
from typing import Generic, Self, TypeVar, cast

from jsonpatch import JsonPatch  # type: ignore[import-untyped]
from ucsschool_objects.core.domain.json import to_json
from ucsschool_objects.core.domain.models import (
    Group,
    School,
    User,
)
from ucsschool_objects.core.domain.ports.manager import JSONPathOperation

_T = TypeVar("_T", School, Group, User)

_EMPTY_FROZENSET: frozenset[str] = frozenset()


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
        JsonPatch.from_diff(
            src_dict, dst_dict
        ).patch  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    )
    return cast(Sequence[JSONPathOperation], JsonPatch(operations).patch)


def _create_patch(
    src: _T, dst: _T, replace_fields: frozenset[str] = _EMPTY_FROZENSET
) -> Sequence[JSONPathOperation]:
    src_dict = to_json(src)
    dst_dict = to_json(dst)
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

    The accumulated changes are available as a JSON Patch via the ``patch``
    property — both inside the ``with`` block (as a live diff against the
    baseline taken on enter) and after it. Dispatches to the appropriate
    ``create_*_patch`` function so that any type-specific logic is applied
    automatically.

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
        self._original: _T | None = None
        self._replace_fields: frozenset[str] = replace_fields

    def __enter__(self) -> Self:
        self._original = copy.deepcopy(self._obj)
        return self

    def __exit__(self, *_: object) -> None:
        pass  # the patch is computed on access — see the ``patch`` property

    @property
    def patch(self) -> Sequence[JSONPathOperation]:
        """JSON Patch transforming the baseline into the object's current state.

        Computed on access, so it can be read inside the ``with`` block as
        well as after it. Empty if nothing changed.

        Raises:
            RuntimeError: If read before the ``with`` block was entered — no
                baseline exists yet at that point.
        """
        if self._original is None:
            raise RuntimeError(
                "tracker.patch requires a baseline; enter the track_changes context first."
            )
        if isinstance(self._obj, School) and isinstance(self._original, School):
            return create_school_patch(self._original, self._obj, self._replace_fields)
        if isinstance(self._obj, Group) and isinstance(self._original, Group):
            return create_group_patch(self._original, self._obj, self._replace_fields)
        if isinstance(self._obj, User) and isinstance(self._original, User):
            return create_user_patch(self._original, self._obj, self._replace_fields)
        raise TypeError(  # pragma: no cover — unreachable: _T is constrained to School | Group | User
            f"track_changes does not support {type(self._obj).__name__} objects."
        )
