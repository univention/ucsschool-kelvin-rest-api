from __future__ import annotations

import uuid
from uuid import UUID

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
        educational_servers=set({"srv"}),
        administrative_servers=set(),
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
        email=None,
        allowed_email_senders_users=UNLOADED,
        allowed_email_senders_groups=UNLOADED,
        member_roles=UNLOADED,
        school=UNLOADED,
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
        allowed_email_senders_users=set(),
        allowed_email_senders_groups=set(),
        member_roles=UNLOADED,
        school=UNLOADED,
    )


def user(
    school_memberships: dict[UUID, SchoolMembership] | UnloadedType = UNLOADED,
    legal_wards: set[User] | UnloadedType = UNLOADED,
    legal_guardians: set[User] | UnloadedType = UNLOADED,
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
