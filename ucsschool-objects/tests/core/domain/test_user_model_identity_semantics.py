from __future__ import annotations

import uuid

import pytest
from tests.core.domain.helpers.model_builders import (
    role as build_role,
    school as build_school,
    school_class as build_school_class,
    user as build_user,
    workgroup as build_workgroup,
)
from ucsschool_objects.core.domain import UNLOADED, Group, Role, School, SchoolMembership, User


def test_user_is_hashable() -> None:
    user = build_user()
    assert hash(user) == hash(user.public_id)
    s: set[User] = {user}
    assert user in s


def test_school_is_hashable() -> None:
    school = build_school()
    assert hash(school) == hash(school.public_id)


def test_role_is_hashable() -> None:
    role = build_role()
    assert hash(role) == hash(role.public_id)


def test_school_class_is_hashable() -> None:
    school_class = build_school_class()
    assert hash(school_class) == hash(school_class.public_id)


def test_workgroup_is_hashable() -> None:
    workgroup = build_workgroup()
    assert hash(workgroup) == hash(workgroup.public_id)


def test_user_equality_by_public_id() -> None:
    uid = uuid.uuid4()
    u1 = User(
        public_id=uid,
        record_uid="a",
        source_uid="b",
        name="x",
        firstname="F",
        lastname="L",
        email=None,
        birthday=None,
        expiration_date=None,
        active=True,
        school_memberships=UNLOADED,
        legal_wards=UNLOADED,
        legal_guardians=UNLOADED,
    )
    u2 = User(
        public_id=uid,
        record_uid="different",
        source_uid="different",
        name="different",
        firstname="F",
        lastname="L",
        email=None,
        birthday=None,
        expiration_date=None,
        active=False,
        school_memberships=UNLOADED,
        legal_wards=UNLOADED,
        legal_guardians=UNLOADED,
    )
    assert u1 == u2


def test_school_minimal_only_loads_public_id() -> None:
    public_id = uuid.uuid4()

    school = School.minimal(public_id)

    assert school.public_id == public_id
    assert isinstance(school.record_uid, type(UNLOADED))
    assert isinstance(school.source_uid, type(UNLOADED))
    assert isinstance(school.name, type(UNLOADED))
    assert isinstance(school.display_name, type(UNLOADED))
    assert isinstance(school.educational_servers, type(UNLOADED))
    assert isinstance(school.administrative_servers, type(UNLOADED))
    assert isinstance(school.class_share_file_server, type(UNLOADED))
    assert isinstance(school.home_share_file_server, type(UNLOADED))


def test_role_minimal_only_loads_public_id() -> None:
    public_id = uuid.uuid4()

    role = Role.minimal(public_id)

    assert role.public_id == public_id
    assert isinstance(role.name, type(UNLOADED))
    assert isinstance(role.display_name, type(UNLOADED))


def test_group_minimal_only_loads_public_id() -> None:
    public_id = uuid.uuid4()

    group = Group.minimal(public_id)

    assert group.public_id == public_id
    assert isinstance(group.record_uid, type(UNLOADED))
    assert isinstance(group.source_uid, type(UNLOADED))
    assert isinstance(group.name, type(UNLOADED))
    assert isinstance(group.display_name, type(UNLOADED))
    assert isinstance(group.create_share, type(UNLOADED))
    assert isinstance(group.roles, type(UNLOADED))
    assert isinstance(group.allowed_email_senders_users, type(UNLOADED))
    assert isinstance(group.allowed_email_senders_groups, type(UNLOADED))
    assert isinstance(group.members, type(UNLOADED))
    assert isinstance(group.member_roles, type(UNLOADED))
    assert isinstance(group.school, type(UNLOADED))
    assert isinstance(group.email, type(UNLOADED))


def test_user_minimal_only_loads_public_id() -> None:
    public_id = uuid.uuid4()

    user = User.minimal(public_id)

    assert user.public_id == public_id
    assert isinstance(user.record_uid, type(UNLOADED))
    assert isinstance(user.source_uid, type(UNLOADED))
    assert isinstance(user.name, type(UNLOADED))
    assert isinstance(user.firstname, type(UNLOADED))
    assert isinstance(user.lastname, type(UNLOADED))
    assert isinstance(user.active, type(UNLOADED))
    assert isinstance(user.school_memberships, type(UNLOADED))
    assert isinstance(user.legal_wards, type(UNLOADED))
    assert isinstance(user.legal_guardians, type(UNLOADED))


def test_role_equality_by_public_id() -> None:
    uid = uuid.uuid4()
    r1 = Role(public_id=uid, name="teacher", display_name={"de": "Lehrer"})
    r2 = Role(public_id=uid, name="other", display_name={"de": "Andere"})

    assert r1 == r2


def test_group_equality_by_public_id() -> None:
    uid = uuid.uuid4()
    g1 = Group(
        public_id=uid,
        record_uid="rg1",
        source_uid="sg1",
        name="class-a",
        display_name=UNLOADED,
        create_share=False,
        roles=UNLOADED,
        email=None,
        allowed_email_senders_users=UNLOADED,
        allowed_email_senders_groups=UNLOADED,
        members=UNLOADED,
        member_roles=UNLOADED,
        school=UNLOADED,
    )
    g2 = Group(
        public_id=uid,
        record_uid="rg2",
        source_uid="sg2",
        name="class-b",
        display_name=UNLOADED,
        create_share=True,
        roles=UNLOADED,
        email=None,
        allowed_email_senders_users=UNLOADED,
        allowed_email_senders_groups=UNLOADED,
        members=UNLOADED,
        member_roles=UNLOADED,
        school=UNLOADED,
    )

    assert g1 == g2


def test_school_membership_equality_uses_school_primary_roles_and_groups() -> None:
    school = build_school()
    role = build_role("teacher")
    group = build_school_class("class-a")

    membership1 = SchoolMembership(
        school=school,
        is_primary=True,
        roles=set({role}),
        groups=set({group}),
    )
    membership2 = SchoolMembership(
        school=school,
        is_primary=True,
        roles=set({role}),
        groups=set({group}),
    )

    assert membership1 == membership2
    assert hash(membership1) == hash(membership2)


def test_school_membership_equality_detects_different_loaded_fields() -> None:
    school = build_school()
    group = build_school_class("class-a")
    role1 = build_role("teacher")
    role2 = build_role("student")

    membership1 = SchoolMembership(
        school=school,
        is_primary=True,
        roles=set({role1}),
        groups=set({group}),
    )
    membership2 = SchoolMembership(
        school=school,
        is_primary=True,
        roles=set({role2}),
        groups=set({group}),
    )

    assert membership1 != membership2
    assert hash(membership1) != hash(membership2)


@pytest.mark.parametrize(
    "entity",
    [
        pytest.param(build_school(), id="school"),
        pytest.param(build_role(), id="role"),
        pytest.param(build_school_class(), id="group"),
        pytest.param(
            SchoolMembership(
                school=build_school(),
                is_primary=True,
                roles=set(),
                groups=set(),
            ),
            id="school-membership",
        ),
        pytest.param(build_user(), id="user"),
    ],
)
def test_model_eq_returns_not_implemented_for_other_types(entity: object) -> None:
    eq_result = entity.__eq__(object())
    assert eq_result is NotImplemented
