from __future__ import annotations

from datetime import date
from uuid import UUID

from ucsschool_objects.database_models import (
    Group as GroupModel,
    School as SchoolModel,
    User as UserModel,
)

from ucsschool.kelvin.corelib.domain import UNLOADED, Group, School, UnloadedType, User


def coerce_date(value: object) -> date | None:
    if value is None:
        return None
    return value if isinstance(value, date) else None


def to_school(model: SchoolModel) -> School:
    return School(
        public_id=model.public_id,
        record_uid=model.record_uid,
        source_uid=model.source_uid,
        name=model.name,
        display_name=dict(model.display_name),
        educational_servers=tuple(model.educational_servers),
        administrative_servers=tuple(model.administrative_servers),
        class_share_file_server=model.class_share_file_server,
        home_share_file_server=model.home_share_file_server,
    )


def to_group(model: GroupModel, *, include_school: bool) -> Group:
    school: School | None | UnloadedType
    if include_school:
        school = to_school(model.school)
    else:
        school = UNLOADED

    return Group(
        public_id=model.public_id,
        record_uid=model.record_uid,
        source_uid=model.source_uid,
        name=model.name,
        display_name=dict(model.display_name),
        has_share=model.has_share,
        email=model.email,
        school=school,
    )


def to_user(model: UserModel, *, include_school: bool, include_groups: bool) -> User:
    school: School | None | UnloadedType = UNLOADED
    groups: tuple[Group, ...] | UnloadedType = UNLOADED

    if include_school:
        primary = next(
            (membership for membership in model.school_memberships if membership.is_primary), None
        )
        if primary is not None:
            school = to_school(primary.school)
        else:
            school = None

    if include_groups:
        by_public_id: dict[UUID, Group] = {}
        for membership in model.school_memberships:
            for group in membership.groups:
                by_public_id[group.public_id] = to_group(group, include_school=False)
        groups = tuple(by_public_id.values())

    return User(
        public_id=model.public_id,
        record_uid=model.record_uid,
        source_uid=model.source_uid,
        name=model.name,
        firstname=model.firstname,
        lastname=model.lastname,
        email=model.email,
        birthday=coerce_date(model.birthday),
        expiration_date=coerce_date(model.expiration_date),
        active=model.active,
        school=school,
        groups=groups,
    )
