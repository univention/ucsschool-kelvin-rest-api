from __future__ import annotations

from collections.abc import Collection, Iterable
from datetime import date, datetime
from typing import TYPE_CHECKING, TypeVar, cast
from uuid import UUID

from sqlalchemy import inspect
from ucsschool_objects.core.domain.models import (
    UNLOADED,
    Group,
    Role,
    School,
    SchoolMembership,
    UnloadedType,
    User,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from ucsschool_objects.database_models import (
        Group as GroupModel,
        Role as RoleModel,
        School as SchoolModel,
        SchoolMembership as SchoolMembershipModel,
        User as UserModel,
    )

TModel = TypeVar("TModel")
TConverted = TypeVar("TConverted")


def _as_str(value: object) -> str:
    return cast(str, value)


def _as_optional_str(value: object) -> str | None:
    return cast(str | None, value)


def _as_bool(value: object) -> bool:
    return cast(bool, value)


def _as_optional_date(value: object) -> date | None:
    # Some drivers (e.g. aiosqlite) may return datetime for DATE columns.
    if value is None:
        return None
    if isinstance(value, datetime):  # pragma: no cover
        return value.date()
    return cast(date, value)


def _as_role_display_name(value: object) -> dict[str, str]:
    return cast(dict[str, str], value)


def _as_set_str(value: object) -> set[str]:
    return set(cast(Iterable[str], value))


def _as_udm_properties(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value)


def _is_loaded(model: object, attribute: str) -> bool:
    state = inspect(model, raiseerr=False)
    if state is None:
        return True
    unloaded = cast(Collection[str] | None, state.unloaded)
    if unloaded is None:
        return True
    return attribute not in unloaded


def _loaded_value(
    model: object,
    attribute: str,
) -> object | UnloadedType:
    if not _is_loaded(model, attribute):
        return UNLOADED
    return cast(object, getattr(model, attribute))


def _convert_loaded(
    value: object | UnloadedType,
    converter: Callable[[object], TConverted],
) -> TConverted | UnloadedType:
    if isinstance(value, UnloadedType):
        return UNLOADED
    return converter(value)


def _convert_unloadable(
    model: object,
    attribute: str,
    converter: Callable[[object], TConverted],
) -> TConverted | UnloadedType:
    return _convert_loaded(_loaded_value(model, attribute), converter)


def to_school(model: SchoolModel) -> School:
    return School(
        public_id=model.public_id,
        record_uid=_convert_unloadable(model, "record_uid", _as_str),
        source_uid=_convert_unloadable(model, "source_uid", _as_str),
        name=_convert_unloadable(model, "name", _as_str),
        display_name=_convert_unloadable(model, "display_name", _as_str),
        educational_servers=_convert_unloadable(model, "educational_servers", _as_set_str),
        administrative_servers=_convert_unloadable(model, "administrative_servers", _as_set_str),
        class_share_file_server=_convert_unloadable(model, "class_share_file_server", _as_optional_str),
        home_share_file_server=_convert_unloadable(model, "home_share_file_server", _as_optional_str),
        udm_properties=_convert_unloadable(model, "udm_properties", _as_udm_properties),
    )


def to_role(model: RoleModel) -> Role:
    return Role(
        public_id=model.public_id,
        name=_convert_unloadable(model, "name", _as_str),
        display_name=_convert_unloadable(model, "display_name", _as_role_display_name),
    )


def to_group(model: GroupModel) -> Group:
    school: School | UnloadedType = UNLOADED
    if _is_loaded(model, "school"):
        school = to_school(model.school)

    roles: set[Role] | UnloadedType = UNLOADED
    if _is_loaded(model, "roles"):
        roles = {to_role(r) for r in model.roles}

    allowed_email_senders_users: set[User] | UnloadedType = UNLOADED
    if _is_loaded(model, "allowed_email_senders_users"):
        allowed_email_senders_users = {
            _to_related_user(user) for user in model.allowed_email_senders_users
        }

    allowed_email_senders_groups: set[Group] | UnloadedType = UNLOADED
    if _is_loaded(model, "allowed_email_senders_groups"):
        allowed_email_senders_groups = {to_group(group) for group in model.allowed_email_senders_groups}

    members: set[User] | UnloadedType = UNLOADED
    if _is_loaded(model, "members"):
        members = {_to_related_user(membership.user) for membership in model.members}

    member_roles: set[Role] | UnloadedType = UNLOADED
    if _is_loaded(model, "member_roles"):
        member_roles = {to_role(role) for role in model.member_roles}

    return Group(
        public_id=model.public_id,
        record_uid=_convert_unloadable(model, "record_uid", _as_str),
        source_uid=_convert_unloadable(model, "source_uid", _as_str),
        name=_convert_unloadable(model, "name", _as_str),
        display_name=_convert_unloadable(model, "display_name", _as_str),
        create_share=_convert_unloadable(model, "has_share", _as_bool),
        roles=roles,
        email=_convert_unloadable(model, "email", _as_optional_str),
        allowed_email_senders_users=allowed_email_senders_users,
        allowed_email_senders_groups=allowed_email_senders_groups,
        members=members,
        member_roles=member_roles,
        school=school,
        description=_convert_unloadable(model, "description", _as_optional_str),
        udm_properties=_convert_unloadable(model, "udm_properties", _as_udm_properties),
    )


def _to_school_membership(model: SchoolMembershipModel) -> SchoolMembership:
    return SchoolMembership(
        school=to_school(model.school),
        is_primary=model.is_primary,
        roles={to_role(role) for role in model.roles},
        groups={to_group(group) for group in model.groups},
    )


def _to_related_user(model: UserModel) -> User:
    return User(
        public_id=model.public_id,
        record_uid=_convert_unloadable(model, "record_uid", _as_str),
        source_uid=_convert_unloadable(model, "source_uid", _as_str),
        name=_convert_unloadable(model, "name", _as_str),
        firstname=_convert_unloadable(model, "firstname", _as_str),
        lastname=_convert_unloadable(model, "lastname", _as_str),
        email=_convert_unloadable(model, "email", _as_optional_str),
        birthday=_convert_unloadable(model, "birthday", _as_optional_date),
        expiration_date=_convert_unloadable(model, "expiration_date", _as_optional_date),
        active=_convert_unloadable(model, "active", _as_bool),
        school_memberships=UNLOADED,
        legal_wards=UNLOADED,
        legal_guardians=UNLOADED,
    )


def _optional_user_relation(models: tuple[UserModel, ...] | list[UserModel]) -> set[User]:
    return {_to_related_user(model) for model in models}


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
        record_uid=_convert_unloadable(model, "record_uid", _as_str),
        source_uid=_convert_unloadable(model, "source_uid", _as_str),
        name=_convert_unloadable(model, "name", _as_str),
        firstname=_convert_unloadable(model, "firstname", _as_str),
        lastname=_convert_unloadable(model, "lastname", _as_str),
        email=_convert_unloadable(model, "email", _as_optional_str),
        birthday=_convert_unloadable(model, "birthday", _as_optional_date),
        expiration_date=_convert_unloadable(model, "expiration_date", _as_optional_date),
        active=_convert_unloadable(model, "active", _as_bool),
        school_memberships=school_memberships,
        legal_wards=legal_wards,
        legal_guardians=legal_guardians,
        udm_properties=_convert_unloadable(model, "udm_properties", _as_udm_properties),
    )


def school_from_patch(patched: dict[str, object], public_id: UUID) -> School:
    return School(
        public_id=public_id,
        record_uid=cast(str, patched["record_uid"]),
        source_uid=cast(str, patched["source_uid"]),
        name=cast(str, patched["name"]),
        display_name=cast(str, patched["display_name"]),
        educational_servers=set(cast(list[str], patched["educational_servers"])),
        administrative_servers=set(cast(list[str], patched["administrative_servers"])),
        class_share_file_server=cast(str | None, patched["class_share_file_server"]),
        home_share_file_server=cast(str | None, patched["home_share_file_server"]),
    )


def group_from_patch(patched: dict[str, object], public_id: UUID) -> Group:
    return Group(
        public_id=public_id,
        record_uid=cast(str, patched["record_uid"]),
        source_uid=cast(str, patched["source_uid"]),
        name=cast(str, patched["name"]),
        display_name=cast(str, patched["display_name"]),
        create_share=cast(bool, patched["create_share"]),
        roles=cast(set[Role], patched["roles"]),
        email=cast(str | None, patched["email"]),
        description=cast(str | None, patched["description"]),
        school=UNLOADED,
        members=UNLOADED,
        member_roles=UNLOADED,
        allowed_email_senders_users=UNLOADED,
        allowed_email_senders_groups=UNLOADED,
    )


def user_from_patch(patched: dict[str, object], public_id: UUID) -> User:
    birthday_val = patched["birthday"]
    expiration_val = patched["expiration_date"]
    return User(
        public_id=public_id,
        record_uid=cast(str, patched["record_uid"]),
        source_uid=cast(str, patched["source_uid"]),
        name=cast(str, patched["name"]),
        firstname=cast(str, patched["firstname"]),
        lastname=cast(str, patched["lastname"]),
        email=cast(str | None, patched["email"]),
        active=cast(bool, patched["active"]),
        birthday=date.fromisoformat(cast(str, birthday_val)) if birthday_val is not None else None,
        expiration_date=date.fromisoformat(cast(str, expiration_val))
        if expiration_val is not None
        else None,
        school_memberships=UNLOADED,
        legal_wards=UNLOADED,
        legal_guardians=UNLOADED,
    )
