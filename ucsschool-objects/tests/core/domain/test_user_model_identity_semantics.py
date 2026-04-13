from __future__ import annotations

import uuid

from tests.core.domain.helpers.model_builders import (
    role as build_role,
    school as build_school,
    school_class as build_school_class,
    user as build_user,
    workgroup as build_workgroup,
)
from ucsschool_objects.core.domain import User


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
