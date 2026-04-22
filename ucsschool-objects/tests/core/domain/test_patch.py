from __future__ import annotations

import copy
import uuid
from datetime import date

from tests.core.domain.helpers.model_builders import (
    role as build_role,
    school as build_school,
    school_class as build_school_class,
    user as build_user,
)
from ucsschool_objects.core.domain.models import SchoolMembership
from ucsschool_objects.core.domain.patch import _create_patch, _normalise, track_changes

# --- _normalise ---


def test_normalise_sorts_flat_list() -> None:
    assert _normalise(["c", "a", "b"]) == ["a", "b", "c"]


def test_normalise_empty_list() -> None:
    assert _normalise([]) == []


def test_normalise_leaves_scalar_unchanged() -> None:
    assert _normalise("hello") == "hello"
    assert _normalise(42) == 42
    assert _normalise(None) is None


def test_normalise_sorts_nested_list_in_dict() -> None:
    result = _normalise({"servers": ["z", "a", "m"]})
    assert result == {"servers": ["a", "m", "z"]}


def test_normalise_sorts_list_of_dicts_by_str() -> None:
    items = [{"name": "z"}, {"name": "a"}]
    result = _normalise(items)
    assert result == sorted(items, key=str)


def test_normalise_converts_set_to_sorted_list() -> None:
    result = _normalise({"c", "a", "b"})
    assert result == ["a", "b", "c"]


def test_normalise_converts_frozenset_to_sorted_list() -> None:
    result = _normalise(frozenset({"c", "a", "b"}))
    assert result == ["a", "b", "c"]


def test_normalise_converts_uuid_to_str() -> None:
    u = uuid.uuid4()
    assert _normalise(u) == str(u)


def test_normalise_converts_uuid_dict_key_to_str() -> None:
    u = uuid.uuid4()
    result = _normalise({u: "value"})
    assert result == {str(u): "value"}


def test_normalise_converts_date_to_isoformat() -> None:
    d = date(2024, 1, 15)
    assert _normalise(d) == "2024-01-15"


def test_normalise_recurses_into_nested_dicts() -> None:
    result = _normalise({"outer": {"inner": ["b", "a"]}})
    assert result == {"outer": {"inner": ["a", "b"]}}


# --- _create_patch ---


def test_create_patch_no_changes_produces_empty_patch() -> None:
    school = build_school()
    patch = _create_patch(school, copy.copy(school))
    assert list(patch) == []


def test_create_patch_scalar_change_produces_replace_op() -> None:
    src = build_school(name="old")
    dst = copy.copy(src)
    dst.name = "new"
    patch = _create_patch(src, dst)
    ops = list(patch)
    assert len(ops) == 1
    assert ops[0] == {"op": "replace", "path": "/name", "value": "new"}


def test_create_patch_set_add_produces_add_op() -> None:
    src = build_school()
    dst = copy.copy(src)
    assert isinstance(src.educational_servers, set)
    dst.educational_servers = src.educational_servers | {"new-server"}
    patch = _create_patch(src, dst)
    paths = [op["path"] for op in patch]
    # element-wise: an add on an index, not a replace on the array root
    assert any(p.startswith("/educational_servers/") for p in paths)
    assert "/educational_servers" not in paths


def test_create_patch_replace_fields_produces_single_replace_op() -> None:
    src = build_school()
    dst = copy.copy(src)
    dst.educational_servers = {"completely", "different"}
    patch = _create_patch(src, dst, replace_fields=frozenset({"educational_servers"}))
    ops = list(patch)
    replace_ops = [o for o in ops if o["path"] == "/educational_servers"]
    assert len(replace_ops) == 1
    assert replace_ops[0]["op"] == "replace"


def test_create_patch_replace_fields_no_change_emits_no_op() -> None:
    src = build_school()
    dst = copy.copy(src)
    patch = _create_patch(src, dst, replace_fields=frozenset({"educational_servers"}))
    paths = [op["path"] for op in patch]
    assert "/educational_servers" not in paths


def test_create_patch_identical_sets_produce_no_op() -> None:
    src = build_school()
    dst = copy.copy(src)
    assert isinstance(src.educational_servers, set)
    dst.educational_servers = set(src.educational_servers)
    patch = _create_patch(src, dst)
    assert list(patch) == []


def test_create_patch_uuid_keyed_dict_change_produces_stable_op() -> None:
    school = build_school()
    role_a = build_role("student")
    role_b = build_role("teacher")
    assert isinstance(school.public_id, uuid.UUID)
    membership = SchoolMembership(school=school, is_primary=True, roles={role_a}, groups=set())
    src = build_user(school_memberships={school.public_id: membership})
    dst = copy.copy(src)
    updated = SchoolMembership(school=school, is_primary=True, roles={role_a, role_b}, groups=set())
    dst.school_memberships = {school.public_id: updated}
    patch = _create_patch(src, dst)
    paths = [op["path"] for op in patch]
    # operations are scoped under the school's UUID key, not a positional index
    assert any(p.startswith(f"/school_memberships/{school.public_id}/") for p in paths)


# --- track_changes ---


def test_track_changes_patch_is_none_before_enter() -> None:
    school = build_school()
    tracker = track_changes(school)
    assert tracker.patch is None


def test_track_changes_no_mutations_produces_empty_patch() -> None:
    school = build_school()
    with track_changes(school) as tracker:
        pass
    assert tracker.patch is not None
    assert list(tracker.patch) == []


def test_track_changes_captures_scalar_mutation() -> None:
    school = build_school(name="before")
    with track_changes(school) as tracker:
        school.name = "after"
    assert tracker.patch is not None
    ops = list(tracker.patch)
    assert any(o["op"] != "remove" and o["path"] == "/name" and o["value"] == "after" for o in ops)


def test_track_changes_dispatches_for_group() -> None:
    group = build_school_class(name="before")
    with track_changes(group) as tracker:
        group.name = "after"
    assert tracker.patch is not None
    ops = list(tracker.patch)
    assert any(o["op"] != "remove" and o["path"] == "/name" and o["value"] == "after" for o in ops)


def test_track_changes_dispatches_for_user() -> None:
    user = build_user()
    with track_changes(user) as tracker:
        user.name = "changed"
    assert tracker.patch is not None
    ops = list(tracker.patch)
    assert any(o["op"] != "remove" and o["path"] == "/name" and o["value"] == "changed" for o in ops)


def test_track_changes_does_not_mutate_original_on_copy() -> None:
    school = build_school(name="original")
    with track_changes(school) as tracker:
        school.name = "mutated"
    assert tracker.patch is not None
    assert any(op["op"] != "remove" and op["value"] == "mutated" for op in tracker.patch)


def test_track_changes_replace_fields_forwarded() -> None:
    school = build_school()
    with track_changes(school, replace_fields=frozenset({"educational_servers"})) as tracker:
        school.educational_servers = {"new"}
    assert tracker.patch is not None
    ops = list(tracker.patch)
    replace_ops = [o for o in ops if o["path"] == "/educational_servers"]
    assert len(replace_ops) == 1
    assert replace_ops[0]["op"] == "replace"
