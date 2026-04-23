from __future__ import annotations

from collections.abc import Callable, Collection, Iterable
from datetime import date
from typing import TypeVar, cast, overload
from uuid import UUID

from sqlalchemy import inspect
from ucsschool_objects.core.domain import (
    UNLOADED,
    Group,
    Role,
    School,
    SchoolMembership,
    UnloadedType,
    User,
)
from ucsschool_objects.database_models import (
    Group as GroupModel,
    Role as RoleModel,
    School as SchoolModel,
    SchoolMembership as SchoolMembershipModel,
    User as UserModel,
)

TTransformed = TypeVar("TTransformed")


def _as_str(value: object) -> str:
    return cast(str, value)


def _as_optional_str(value: object) -> str | None:
    return cast(str | None, value)


def _as_bool(value: object) -> bool:
    return cast(bool, value)


def _as_optional_date(value: object) -> date | None:
    return cast(date | None, value)


def _as_display_name(value: object) -> dict[str, str]:
    return dict(cast(dict[str, str], value))


def _as_set_str(value: object) -> set[str]:
    return set(cast(Iterable[str], value))


def _is_loaded(model: object, attribute: str) -> bool:
    state = inspect(model, raiseerr=False)
    if state is None:
        return True
    unloaded = getattr(state, "unloaded", None)
    if unloaded is None:
        return True
    return attribute not in cast(Collection[str], unloaded)


@overload
def _loaded_value(
    model: object,
    attribute: str,
    transform: None = None,
) -> object | UnloadedType:
    ...  # pragma: no cover


@overload
def _loaded_value(
    model: object,
    attribute: str,
    transform: Callable[[object], TTransformed],
) -> TTransformed | UnloadedType:
    ...  # pragma: no cover


def _loaded_value(
    model: object,
    attribute: str,
    transform: Callable[[object], TTransformed] | None = None,
) -> object | TTransformed | UnloadedType:
    if not _is_loaded(model, attribute):
        return UNLOADED

    value = cast(object, getattr(model, attribute))
    if transform is None:
        return value
    return transform(value)


def to_school(model: SchoolModel) -> School:
    return School(
        public_id=model.public_id,
        record_uid=_loaded_value(model, "record_uid", _as_str),
        source_uid=_loaded_value(model, "source_uid", _as_str),
        name=_loaded_value(model, "name", _as_str),
        display_name=_loaded_value(model, "display_name", _as_display_name),
        educational_servers=_loaded_value(model, "educational_servers", _as_set_str),
        administrative_servers=_loaded_value(
            model,
            "administrative_servers",
            _as_set_str,
        ),
        class_share_file_server=_loaded_value(model, "class_share_file_server", _as_optional_str),
        home_share_file_server=_loaded_value(model, "home_share_file_server", _as_optional_str),
    )


def to_role(model: RoleModel) -> Role:
    return Role(
        public_id=model.public_id,
        name=_loaded_value(model, "name", _as_str),
        display_name=_loaded_value(model, "display_name", _as_display_name),
    )


def to_group(model: GroupModel) -> Group:
    school: School | UnloadedType = UNLOADED
    if _is_loaded(model, "school"):
        school = to_school(model.school)

    group_type: str | UnloadedType = UNLOADED
    if _is_loaded(model, "group_type"):
        group_type = model.group_type.name

    allowed_email_senders_users: set[str] | UnloadedType = UNLOADED
    if _is_loaded(model, "allowed_email_senders_users"):
        allowed_email_senders_users = set(user.name for user in model.allowed_email_senders_users)

    allowed_email_senders_groups: set[str] | UnloadedType = UNLOADED
    if _is_loaded(model, "allowed_email_senders_groups"):
        allowed_email_senders_groups = set(group.name for group in model.allowed_email_senders_groups)

    member_roles: set[Role] | UnloadedType = UNLOADED
    if _is_loaded(model, "member_roles"):
        member_roles = set(to_role(role) for role in model.member_roles)

    return Group(
        public_id=model.public_id,
        record_uid=_loaded_value(model, "record_uid", _as_str),
        source_uid=_loaded_value(model, "source_uid", _as_str),
        name=_loaded_value(model, "name", _as_str),
        display_name=_loaded_value(model, "display_name", _as_display_name),
        create_share=_loaded_value(model, "has_share", _as_bool),
        group_type=group_type,
        email=_loaded_value(model, "email", _as_optional_str),
        allowed_email_senders_users=allowed_email_senders_users,
        allowed_email_senders_groups=allowed_email_senders_groups,
        member_roles=member_roles,
        school=school,
    )


def _to_school_membership(
    model: SchoolMembershipModel,
) -> SchoolMembership:
    return SchoolMembership(
        school=to_school(model.school),
        is_primary=model.is_primary,
        roles=set(to_role(r) for r in model.roles),
        groups=set(to_group(group) for group in model.groups),
    )


def _to_related_user(model: UserModel) -> User:
    return User(
        public_id=model.public_id,
        record_uid=_loaded_value(model, "record_uid", _as_str),
        source_uid=_loaded_value(model, "source_uid", _as_str),
        name=_loaded_value(model, "name", _as_str),
        firstname=_loaded_value(model, "firstname", _as_str),
        lastname=_loaded_value(model, "lastname", _as_str),
        email=_loaded_value(model, "email", _as_optional_str),
        birthday=_loaded_value(model, "birthday", _as_optional_date),
        expiration_date=_loaded_value(model, "expiration_date", _as_optional_date),
        active=_loaded_value(model, "active", _as_bool),
        school_memberships=UNLOADED,
        legal_wards=UNLOADED,
        legal_guardians=UNLOADED,
    )


def _optional_user_relation(models: tuple[UserModel, ...] | list[UserModel]) -> set[User]:
    return set(_to_related_user(model) for model in models)


def to_user(
    model: UserModel,
    *,
    include_memberships: bool,
    include_legal_wards: bool,
    include_legal_guardians: bool,
) -> User:
    school_memberships: dict[UUID, SchoolMembership] | UnloadedType = UNLOADED

    if include_memberships:
        school_memberships = {}
        for membership in (_to_school_membership(m) for m in model.school_memberships):
            school_public_id = membership.school.public_id
            if not isinstance(school_public_id, UUID):
                raise ValueError("Mapped school membership has no UUID school public_id.")
            school_memberships[school_public_id] = membership

    legal_wards: set[User] | UnloadedType = UNLOADED
    if include_legal_wards:
        legal_wards = _optional_user_relation(model.legal_wards)

    legal_guardians: set[User] | UnloadedType = UNLOADED
    if include_legal_guardians:
        legal_guardians = _optional_user_relation(model.legal_guardians)

    return User(
        public_id=model.public_id,
        record_uid=_loaded_value(model, "record_uid", _as_str),
        source_uid=_loaded_value(model, "source_uid", _as_str),
        name=_loaded_value(model, "name", _as_str),
        firstname=_loaded_value(model, "firstname", _as_str),
        lastname=_loaded_value(model, "lastname", _as_str),
        email=_loaded_value(model, "email", _as_optional_str),
        birthday=_loaded_value(model, "birthday", _as_optional_date),
        expiration_date=_loaded_value(model, "expiration_date", _as_optional_date),
        active=_loaded_value(model, "active", _as_bool),
        school_memberships=school_memberships,
        legal_wards=legal_wards,
        legal_guardians=legal_guardians,
    )
