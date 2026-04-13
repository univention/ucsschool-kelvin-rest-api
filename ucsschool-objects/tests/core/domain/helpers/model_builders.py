from __future__ import annotations

import uuid

from ucsschool_objects.core.domain import (
    UNLOADED,
    Role,
    School,
    SchoolMembership,
    UnloadedType,
    User,
)
from ucsschool_objects.core.domain.models import SchoolClass, WorkGroup


def school(name: str = "testschool") -> School:
    return School(
        public_id=uuid.uuid4(),
        record_uid="r1",
        source_uid="s1",
        name=name,
        display_name={},
        educational_servers=("srv",),
        administrative_servers=(),
        class_share_file_server=None,
        home_share_file_server=None,
    )


def role(name: str = "teacher") -> Role:
    return Role(public_id=uuid.uuid4(), name=name, display_name={})


def school_class(name: str = "class1") -> SchoolClass:
    return SchoolClass(
        public_id=uuid.uuid4(),
        record_uid="rg",
        source_uid="sg",
        name=name,
        display_name={},
        create_share=False,
        group_type="school_class",
    )


def workgroup(name: str = "wg1") -> WorkGroup:
    return WorkGroup(
        public_id=uuid.uuid4(),
        record_uid="rwg",
        source_uid="swg",
        name=name,
        display_name={},
        create_share=False,
        group_type="workgroup",
        email=None,
        allowed_email_senders_users=(),
        allowed_email_senders_groups=(),
    )


def user(
    school_memberships: tuple[SchoolMembership, ...] | UnloadedType = UNLOADED,
    legal_wards: tuple[User, ...] | UnloadedType = UNLOADED,
    legal_guardians: tuple[User, ...] | UnloadedType = UNLOADED,
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
