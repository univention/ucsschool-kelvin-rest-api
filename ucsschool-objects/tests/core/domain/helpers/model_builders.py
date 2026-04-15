from __future__ import annotations

import uuid

from ucsschool_objects.core.domain import (
    UNLOADED,
    Group,
    Role,
    School,
    SchoolMembership,
    UnloadedType,
    User,
)


def school(name: str = "testschool") -> School:
    return School(
        public_id=uuid.uuid4(),
        record_uid="r1",
        source_uid="s1",
        name=name,
        display_name={},
        educational_servers=frozenset({"srv"}),
        administrative_servers=frozenset(),
        class_share_file_server=None,
        home_share_file_server=None,
    )


def role(name: str = "teacher") -> Role:
    return Role(public_id=uuid.uuid4(), name=name, display_name={})


def school_class(name: str = "class1") -> Group:
    return Group(
        public_id=uuid.uuid4(),
        record_uid="rg",
        source_uid="sg",
        name=name,
        display_name={},
        create_share=False,
        group_type="school_class",
    )


def workgroup(name: str = "wg1") -> Group:
    return Group(
        public_id=uuid.uuid4(),
        record_uid="rwg",
        source_uid="swg",
        name=name,
        display_name={},
        create_share=False,
        group_type="workgroup",
        email=None,
        allowed_email_senders_users=frozenset(),
        allowed_email_senders_groups=frozenset(),
    )


def user(
    school_memberships: frozenset[SchoolMembership] | UnloadedType = UNLOADED,
    legal_wards: frozenset[User] | UnloadedType = UNLOADED,
    legal_guardians: frozenset[User] | UnloadedType = UNLOADED,
) -> User:
    return User(
        public_id=uuid.uuid4(),
        record_uid="ru",
        source_uid="su",
        name="testuser",
        firstname="Test",
        lastname="User",
        email=None,
        birthday=None,
        expiration_date=None,
        active=True,
        school_memberships=school_memberships,
        legal_wards=legal_wards,
        legal_guardians=legal_guardians,
    )
