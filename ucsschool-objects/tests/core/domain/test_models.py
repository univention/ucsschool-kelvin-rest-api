from __future__ import annotations

import uuid
from datetime import date
from typing import cast
from uuid import UUID

import pytest
from tests.core.domain.helpers.model_builders import (
    school as build_school,
    school_class as build_school_class,
    user as build_user,
)
from ucsschool_objects import (
    UNLOADED,
    Group,
    Role,
    School,
    SchoolMembership,
    User,
)
from ucsschool_objects.core.domain.models import domain_asdict, is_loaded


def test_domain_asdict_serializes_list_tuple_and_frozenset() -> None:
    payload = {
        "items": [
            ("alpha", frozenset({"beta", "gamma"})),
            ["delta", "epsilon"],
        ]
    }

    serialized = domain_asdict(payload)

    items = cast(list[object], serialized["items"])
    first_tuple = cast(tuple[object, object], items[0])
    assert isinstance(first_tuple, tuple)
    assert first_tuple[0] == "alpha"
    assert sorted(cast(list[str], first_tuple[1])) == ["beta", "gamma"]

    second_list = cast(list[str], items[1])
    assert second_list == ["delta", "epsilon"]


def test_domain_asdict_strips_private_field_prefix_for_dataclasses() -> None:
    school = build_school("alpha")

    serialized = domain_asdict(school)

    assert "name" in serialized
    assert "_name" not in serialized
    assert serialized["name"] == "alpha"


def test_is_loaded_reports_state_and_missing_field() -> None:
    loaded_school = build_school("loaded")
    unloaded_school = School.minimal(uuid.uuid4())

    assert is_loaded(loaded_school, "name") is True
    assert is_loaded(unloaded_school, "name") is False

    with pytest.raises(AttributeError, match="has no attribute"):
        _ = is_loaded(loaded_school, "does_not_exist")


def test_school_setters_update_values() -> None:
    school = School.minimal(uuid.uuid4())

    school.record_uid = "record-updated"
    school.source_uid = "source-updated"
    school.display_name = "Display Updated"
    school.administrative_servers = {"adm1", "adm2"}
    school.class_share_file_server = "srv-class"
    school.home_share_file_server = "srv-home"

    assert school.record_uid == "record-updated"
    assert school.source_uid == "source-updated"
    assert school.display_name == "Display Updated"
    assert school.administrative_servers == {"adm1", "adm2"}
    assert school.class_share_file_server == "srv-class"
    assert school.home_share_file_server == "srv-home"


def test_group_setters_update_values() -> None:
    group = Group.minimal(uuid.uuid4())

    group.record_uid = "group-record"
    group.source_uid = "group-source"
    group.display_name = "Group Display"
    group.email = "group@example.com"

    assert group.record_uid == "group-record"
    assert group.source_uid == "group-source"
    assert group.display_name == "Group Display"
    assert group.email == "group@example.com"


def test_user_setters_update_values() -> None:
    school = build_school("school-a")
    school_id = cast(UUID, school.public_id)
    membership = SchoolMembership(school=school, is_primary=True, roles=set(), groups=set())
    user = User.minimal(uuid.uuid4())

    user.record_uid = "user-record"
    user.source_uid = "user-source"
    user.firstname = "First"
    user.lastname = "Last"
    user.active = True
    user.school_memberships = {school_id: membership}
    user.legal_wards = set()
    user.legal_guardians = set()
    user.expiration_date = date(2030, 1, 1)

    assert user.record_uid == "user-record"
    assert user.source_uid == "user-source"
    assert user.firstname == "First"
    assert user.lastname == "Last"
    assert user.active is True
    assert user.school_memberships == {school_id: membership}
    assert user.legal_wards == set()
    assert user.legal_guardians == set()
    assert user.expiration_date == date(2030, 1, 1)


def test_school_membership_equality_notimplemented_with_other_types() -> None:
    school = build_school("school-b")
    role = Role(public_id=uuid.uuid4(), name="teacher", display_name={})
    group = build_school_class("class-b")
    membership = SchoolMembership(school=school, is_primary=True, roles={role}, groups={group})

    assert membership.__eq__(object()) is NotImplemented


def test_user_groups_union_across_memberships() -> None:
    school1 = build_school("school-1")
    school2 = build_school("school-2")
    school1_id = cast(UUID, school1.public_id)
    school2_id = cast(UUID, school2.public_id)
    shared_group = build_school_class("shared")
    only_first = build_school_class("only-first")
    only_second = build_school_class("only-second")

    membership_1 = SchoolMembership(
        school=school1,
        is_primary=True,
        roles=set(),
        groups={shared_group, only_first},
    )
    membership_2 = SchoolMembership(
        school=school2,
        is_primary=False,
        roles=set(),
        groups={shared_group, only_second},
    )

    user = build_user(
        school_memberships={
            school1_id: membership_1,
            school2_id: membership_2,
        }
    )

    assert user.groups == {shared_group, only_first, only_second}


def test_domain_asdict_handles_nested_model_collections() -> None:
    school = build_school("school-c")
    user = build_user()
    group = build_school_class("class-c")
    role = Role(public_id=uuid.uuid4(), name="student", display_name={})
    membership = SchoolMembership(school=school, is_primary=True, roles={role}, groups={group})

    payload = {
        "school_memberships": {school.public_id: membership},
        "users": [user],
        "maybe": UNLOADED,
    }

    serialized = domain_asdict(payload)

    assert "school_memberships" in serialized
    assert "users" in serialized
    assert serialized["maybe"] is UNLOADED
