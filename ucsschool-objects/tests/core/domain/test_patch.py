from __future__ import annotations

import copy
import uuid

import pytest
from tests.core.domain.helpers.model_builders import (
    role as build_role,
    school as build_school,
    school_class as build_school_class,
    user as build_user,
)
from ucsschool_objects.core.domain.models import SchoolMembership, User
from ucsschool_objects.core.domain.patch import _create_patch, _patch_ops, track_changes

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


def _membership_user_pair() -> tuple[User, User, uuid.UUID]:
    """A user with one membership carrying a group, plus a deep copy to mutate."""
    school = build_school()
    group = build_school_class()
    membership = SchoolMembership(school=school, is_primary=True, roles=set(), groups={group})
    assert isinstance(school.public_id, uuid.UUID)
    src = build_user(school_memberships={school.public_id: membership})
    dst = copy.deepcopy(src)
    return src, dst, school.public_id


_MEMBERSHIP_REPLACE_FIELDS = frozenset({"school_memberships/*/groups", "school_memberships/*/roles"})


def test_create_patch_deep_replace_field_produces_atomic_replace_op() -> None:
    src, dst, school_id = _membership_user_pair()
    dst.school_memberships[school_id].groups = {build_school_class(name="other")}
    patch = _create_patch(src, dst, replace_fields=_MEMBERSHIP_REPLACE_FIELDS)
    ops = list(patch)
    assert len(ops) == 1
    assert ops[0]["op"] == "replace"
    assert ops[0]["path"] == f"/school_memberships/{school_id}/groups"
    # no operation reaches inside a referenced group
    assert not any(op["path"].count("/") > 3 for op in ops)


def test_create_patch_deep_replace_field_ignores_reference_load_depth() -> None:
    # The same group link serialized at different load depths (roles loaded
    # vs UNLOADED) is not a change: references compare by public_id only.
    src, dst, school_id = _membership_user_pair()
    (group,) = dst.school_memberships[school_id].groups
    group.roles = {build_role()}
    patch = _create_patch(src, dst, replace_fields=_MEMBERSHIP_REPLACE_FIELDS)
    assert list(patch) == []


def test_create_patch_deep_replace_field_keeps_collections_on_added_membership() -> None:
    src, dst, _ = _membership_user_pair()
    new_school = build_school(name="otherschool")
    assert isinstance(new_school.public_id, uuid.UUID)
    dst.school_memberships[new_school.public_id] = SchoolMembership(
        school=new_school, is_primary=False, roles={build_role()}, groups={build_school_class()}
    )
    patch = _create_patch(src, dst, replace_fields=_MEMBERSHIP_REPLACE_FIELDS)
    add_ops = [op for op in patch if op["op"] == "add"]
    assert len(add_ops) == 1
    assert add_ops[0]["path"] == f"/school_memberships/{new_school.public_id}"
    # the whole-membership add still carries its groups and roles
    added = add_ops[0]["value"]
    assert isinstance(added, dict)
    groups, roles = added["groups"], added["roles"]
    assert isinstance(groups, list) and len(groups) == 1
    assert isinstance(roles, list) and len(roles) == 1


def test_create_patch_top_level_reference_field_compares_by_public_id() -> None:
    ward = build_user()
    src = build_user(legal_wards={ward})
    dst = copy.deepcopy(src)
    (dst_ward,) = dst.legal_wards
    dst_ward.name = "renamed"
    patch = _create_patch(src, dst, replace_fields=frozenset({"legal_wards"}))
    assert list(patch) == []


def test_patch_ops_deep_replace_skips_non_dict_children() -> None:
    ops = _patch_ops(
        {"memberships": "not-a-dict"},
        {"memberships": {"k": {"groups": []}}},
        replace_fields=frozenset({"memberships/*/groups"}),
    )
    # the deep path cannot descend, so jsonpatch handles the difference
    assert [op["path"] for op in ops] == ["/memberships"]


def test_patch_ops_wildcard_skips_non_dict_entries() -> None:
    ops = _patch_ops(
        {"memberships": {"k": "not-a-dict"}},
        {"memberships": {"k": {"groups": ["x"]}}},
        replace_fields=frozenset({"memberships/*/groups"}),
    )
    assert [op["path"] for op in ops] == ["/memberships/k"]


def test_patch_ops_reference_key_mixed_list_compares_verbatim() -> None:
    # lists that are not pure reference collections compare by value
    ops = _patch_ops(
        {"items": [{"public_id": "1"}, "plain"]},
        {"items": ["plain", {"public_id": "1"}]},
        replace_fields=frozenset({"items"}),
    )
    assert [op["path"] for op in ops] == ["/items"]


def test_patch_ops_reference_key_unset_public_id_compares_verbatim() -> None:
    # an UNSET public_id serialises to a sentinel dict — no usable identity,
    # so such lists compare by value instead of by public_id
    unset_ref = {"public_id": {"__sentinel__": "UNSET"}, "name": "a"}
    changed_ref = {"public_id": {"__sentinel__": "UNSET"}, "name": "b"}
    ops = _patch_ops(
        {"items": [unset_ref]},
        {"items": [changed_ref]},
        replace_fields=frozenset({"items"}),
    )
    assert [op["path"] for op in ops] == ["/items"]


def test_patch_ops_single_reference_dict_compares_by_public_id() -> None:
    ops = _patch_ops(
        {"school": {"public_id": "1", "name": "loaded"}, "other": {"no_id": 1}},
        {"school": {"public_id": "1"}, "other": {"no_id": 2}},
        replace_fields=frozenset({"school", "other"}),
    )
    # same school reference despite different load depth; "other" is not a
    # reference dict and compares by value
    assert [op["path"] for op in ops] == ["/other"]


# --- track_changes ---


def test_track_changes_patch_before_enter_raises() -> None:
    school = build_school()
    tracker = track_changes(school)
    with pytest.raises(RuntimeError, match="baseline"):
        tracker.patch


def test_track_changes_patch_is_readable_inside_the_block() -> None:
    school = build_school(name="before")
    with track_changes(school) as tracker:
        assert list(tracker.patch) == []
        school.name = "after"
        ops = list(tracker.patch)
    assert any(o["op"] != "remove" and o["path"] == "/name" and o["value"] == "after" for o in ops)


def test_track_changes_no_mutations_produces_empty_patch() -> None:
    school = build_school()
    with track_changes(school) as tracker:
        pass
    assert list(tracker.patch) == []


def test_track_changes_captures_scalar_mutation() -> None:
    school = build_school(name="before")
    with track_changes(school) as tracker:
        school.name = "after"
    ops = list(tracker.patch)
    assert any(o["op"] != "remove" and o["path"] == "/name" and o["value"] == "after" for o in ops)


def test_track_changes_dispatches_for_group() -> None:
    group = build_school_class(name="before")
    with track_changes(group) as tracker:
        group.name = "after"
    ops = list(tracker.patch)
    assert any(o["op"] != "remove" and o["path"] == "/name" and o["value"] == "after" for o in ops)


def test_track_changes_dispatches_for_user() -> None:
    user = build_user()
    with track_changes(user) as tracker:
        user.name = "changed"
    ops = list(tracker.patch)
    assert any(o["op"] != "remove" and o["path"] == "/name" and o["value"] == "changed" for o in ops)


def test_track_changes_does_not_mutate_original_on_copy() -> None:
    school = build_school(name="original")
    with track_changes(school) as tracker:
        school.name = "mutated"
    assert any(op["op"] != "remove" and op["value"] == "mutated" for op in tracker.patch)


def test_track_changes_replace_fields_forwarded() -> None:
    school = build_school()
    with track_changes(school, replace_fields=frozenset({"educational_servers"})) as tracker:
        school.educational_servers = {"new"}
    ops = list(tracker.patch)
    replace_ops = [o for o in ops if o["path"] == "/educational_servers"]
    assert len(replace_ops) == 1
    assert replace_ops[0]["op"] == "replace"
