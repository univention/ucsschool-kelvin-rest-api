import copy
from collections.abc import Sequence
from typing import Generic, Self, TypeVar, cast

from jsonpatch import JsonPatch  # type: ignore[import-untyped]
from ucsschool_objects.core.domain.json import PatchDict, to_json
from ucsschool_objects.core.domain.models import (
    Group,
    School,
    User,
)
from ucsschool_objects.core.domain.ports.manager import JSONPathOperation

_T = TypeVar("_T", School, Group, User)

_EMPTY_FROZENSET: frozenset[str] = frozenset()


def _reference_key(value: object) -> object:
    """Reduce serialized domain references to their identity for comparison.

    Managers resolve patch values by public_id alone, so two serialisations
    of the same link set must compare equal even when the referenced objects
    were loaded to different depths. A list of reference dicts compares as
    the set of public_ids, a single reference dict as its public_id, and
    anything else verbatim.
    """
    if isinstance(value, list):
        items = cast("list[object]", value)
        keys = [cast(PatchDict, item).get("public_id") for item in items if isinstance(item, dict)]
        # Only str public_ids: an UNSET public_id serialises to a sentinel
        # dict, which has no usable identity.
        if len(keys) == len(items) and all(isinstance(key, str) for key in keys):
            return frozenset(cast("list[str]", keys))
    if isinstance(value, dict):
        dict_value = cast(PatchDict, value)
        if "public_id" in dict_value:
            return dict_value["public_id"]
    return value


def _pop_replace_op(
    src: PatchDict,
    dst: PatchDict,
    field: str,
    path: str,
    operations: list[dict[str, object]],
) -> None:
    src_val = src.pop(field, None)
    dst_val = dst.pop(field, None)
    if _reference_key(src_val) != _reference_key(dst_val):
        operations.append({"op": "replace", "path": path, "value": dst_val})


def _collect_replace_ops(
    src: PatchDict,
    dst: PatchDict,
    parts: list[str],
    prefix: str,
    operations: list[dict[str, object]],
) -> None:
    head = parts[0]
    if len(parts) == 1:
        _pop_replace_op(src, dst, head, f"{prefix}/{head}", operations)
        return
    if head == "*":
        # Only keys present on both sides: a key only in dst belongs to a
        # whole-entry add (which must keep its collections inline), a key
        # only in src to a whole-entry remove.
        for key in sorted(src.keys() & dst.keys()):
            _descend_replace_ops(src[key], dst[key], parts[1:], f"{prefix}/{key}", operations)
        return
    _descend_replace_ops(src.get(head), dst.get(head), parts[1:], f"{prefix}/{head}", operations)


def _descend_replace_ops(
    src_child: object,
    dst_child: object,
    parts: list[str],
    prefix: str,
    operations: list[dict[str, object]],
) -> None:
    if isinstance(src_child, dict) and isinstance(dst_child, dict):
        _collect_replace_ops(
            cast(PatchDict, src_child), cast(PatchDict, dst_child), parts, prefix, operations
        )


def _patch_ops(
    src_dict: dict[str, object],
    dst_dict: dict[str, object],
    replace_fields: frozenset[str] = _EMPTY_FROZENSET,
) -> Sequence[JSONPathOperation]:
    operations: list[dict[str, object]] = []
    for field_path in sorted(replace_fields):
        _collect_replace_ops(src_dict, dst_dict, field_path.split("/"), "", operations)
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
        replace_fields: Fields whose collection value should be replaced atomically
            rather than diffed element-wise. Use this when the intent is to overwrite
            the whole collection, not add or remove individual members — element-wise
            diffs of reference collections can otherwise produce nested operations
            inside the referenced objects, which managers reject. Entries are
            slash-separated paths; ``*`` matches every dict key present on both
            sides (e.g. ``school_memberships/*/groups``). Reference collections are
            compared by public_id, so loading the referenced objects to different
            depths does not count as a change.
    """
    return _create_patch(src, dst, replace_fields)


def create_group_patch(
    src: Group, dst: Group, replace_fields: frozenset[str] = _EMPTY_FROZENSET
) -> Sequence[JSONPathOperation]:
    """Return a JSON Patch describing the changes needed to transform src into dst.

    Args:
        src: The group in its current state (the baseline).
        dst: The group in its desired state (the target).
        replace_fields: Fields whose collection value should be replaced atomically
            rather than diffed element-wise — see ``create_school_patch``.
    """
    return _create_patch(src, dst, replace_fields)


def create_user_patch(
    src: User, dst: User, replace_fields: frozenset[str] = _EMPTY_FROZENSET
) -> Sequence[JSONPathOperation]:
    """Return a JSON Patch describing the changes needed to transform src into dst.

    Args:
        src: The user in its current state (the baseline).
        dst: The user in its desired state (the target).
        replace_fields: Fields whose collection value should be replaced atomically
            rather than diffed element-wise — see ``create_school_patch``.
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
