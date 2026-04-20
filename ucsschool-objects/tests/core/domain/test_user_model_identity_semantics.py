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
from ucsschool_objects.core.domain import Group, Role, SchoolMembership, User


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
    )
    assert u1 == u2


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
        display_name={},
        create_share=False,
        group_type="school_class",
    )
    g2 = Group(
        public_id=uid,
        record_uid="rg2",
        source_uid="sg2",
        name="class-b",
        display_name={},
        create_share=True,
        group_type="school_class",
    )

    assert g1 == g2


def test_school_membership_equality_uses_school_primary_roles_and_groups() -> None:
    school = build_school()
    role = build_role("teacher")
    group = build_school_class("class-a")

    membership1 = SchoolMembership(
        school=school,
        is_primary=True,
        roles=frozenset({role}),
        groups=frozenset({group}),
    )
    membership2 = SchoolMembership(
        school=school,
        is_primary=True,
        roles=frozenset({role}),
        groups=frozenset({group}),
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
        roles=frozenset({role1}),
        groups=frozenset({group}),
    )
    membership2 = SchoolMembership(
        school=school,
        is_primary=True,
        roles=frozenset({role2}),
        groups=frozenset({group}),
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
                roles=frozenset(),
                groups=frozenset(),
            ),
            id="school-membership",
        ),
        pytest.param(build_user(), id="user"),
    ],
)
def test_model_eq_returns_not_implemented_for_other_types(entity: object) -> None:
    eq_result = entity.__eq__(object())
    assert eq_result is NotImplemented
