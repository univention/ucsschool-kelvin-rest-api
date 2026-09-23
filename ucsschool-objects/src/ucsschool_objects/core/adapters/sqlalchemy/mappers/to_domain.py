# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from collections.abc import Collection, Iterable
from datetime import date, datetime
from typing import TYPE_CHECKING, TypeVar, cast
from uuid import UUID

from sqlalchemy import inspect

from ucsschool_objects.core.domain.json import PatchDict
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


def _unloaded_attributes(model: object) -> Collection[str]:
    """Names of the attributes that are not currently loaded on ``model``.

    ``InstanceState.unloaded`` is a computed property: every read of it builds
    a fresh set and diffs it twice. The mappers below ask about every attribute
    of every mapped object, so it is resolved once per instance here and passed
    down, instead of once per attribute.

    Only valid for as long as nothing triggers a lazy load on ``model`` — the
    mappers below never touch an attribute this reports as unloaded, so the
    answer stays accurate for the duration of one mapping call.
    """
    state = inspect(model, raiseerr=False)
    if state is None:
        return ()
    unloaded = cast(Collection[str] | None, state.unloaded)
    if unloaded is None:
        return ()
    return unloaded


def _convert_unloadable(
    model: object,
    unloaded: Collection[str],
    attribute: str,
    converter: Callable[[object], TConverted],
) -> TConverted | UnloadedType:
    if attribute in unloaded:
        return UNLOADED
    return converter(cast(object, getattr(model, attribute)))


class ConversionCache:
    """Memo of the ORM rows already converted during one mapping pass.

    A result set repeats its related rows, so a collection re-converts the same
    School, Role and Group rows many times over. Convert each once and copy.

    Entries are keyed on the ORM instance, which keeps it alive, so an identity
    cannot be reused underneath them. Only valid while the rows behind them are
    unchanged -- one conversion pass.

    Only rows that can repeat are worth memoizing. A search yields each row of
    the type it selects exactly once, so those conversions pass
    ``memoize=False``: storing them would pay for the entry and the copy
    without ever being read back. They still pass the cache down, because the
    rows hanging off them do repeat.
    """

    __slots__: tuple[str, ...] = ("groups", "roles", "schools")

    def __init__(self) -> None:
        self.schools: dict[SchoolModel, School] = {}
        self.roles: dict[RoleModel, Role] = {}
        self.groups: dict[GroupModel, Group] = {}


# Each _clone_* mirrors its to_* counterpart: it rebuilds exactly what the
# builder allocates fresh on every call, and shares what the builder shares.
# Copying more would change behaviour, and cost more than rebuilding.


def _clone_school(school: School) -> School:
    """Copy a cached School.

    ``to_school`` builds a new set for the two server lists per call but hands
    out the ORM instance's own dict for ``udm_properties``, so this does too.
    """
    values: dict[str, object] = school.__dict__.copy()
    for attribute in ("_educational_servers", "_administrative_servers"):
        servers = values[attribute]
        if isinstance(servers, set):
            values[attribute] = set(cast("set[str]", servers))
    clone = object.__new__(School)
    clone.__dict__ = values
    return clone


def _clone_role(role: Role) -> Role:
    """Copy a cached Role.

    ``to_role`` passes ``display_name`` through uncopied, so the clone shares
    that dict with the cached original.
    """
    clone = object.__new__(Role)
    clone.__dict__ = role.__dict__.copy()
    return clone


def _clone_related_user(user: User) -> User:
    """Copy a User as ``_to_related_user`` builds one: scalars, no relations."""
    clone = object.__new__(User)
    clone.__dict__ = user.__dict__.copy()
    return clone


def _clone_group(group: Group) -> Group:
    """Copy a cached Group, down to its own School and its own relation sets."""
    values: dict[str, object] = group.__dict__.copy()
    school = values["_school"]
    if isinstance(school, School):
        values["_school"] = _clone_school(school)
    for attribute in ("_roles", "_member_roles"):
        roles = values[attribute]
        if isinstance(roles, set):
            values[attribute] = {_clone_role(role) for role in cast("set[Role]", roles)}
    for attribute in ("_members", "_allowed_email_senders_users"):
        users = values[attribute]
        if isinstance(users, set):
            values[attribute] = {_clone_related_user(user) for user in cast("set[User]", users)}
    sender_groups = values["_allowed_email_senders_groups"]
    if isinstance(sender_groups, set):
        values["_allowed_email_senders_groups"] = {
            _clone_group(sender) for sender in cast("set[Group]", sender_groups)
        }
    clone = object.__new__(Group)
    clone.__dict__ = values
    return clone


def to_school(
    model: SchoolModel,
    cache: ConversionCache | None = None,
    *,
    memoize: bool = True,
) -> School:
    if cache is not None and memoize and (cached := cache.schools.get(model)) is not None:
        return _clone_school(cached)
    unloaded = _unloaded_attributes(model)
    school = School(
        public_id=model.public_id,
        record_uid=_convert_unloadable(model, unloaded, "record_uid", _as_str),
        source_uid=_convert_unloadable(model, unloaded, "source_uid", _as_str),
        name=_convert_unloadable(model, unloaded, "name", _as_str),
        display_name=_convert_unloadable(model, unloaded, "display_name", _as_str),
        educational_servers=_convert_unloadable(model, unloaded, "educational_servers", _as_set_str),
        administrative_servers=_convert_unloadable(
            model, unloaded, "administrative_servers", _as_set_str
        ),
        class_share_file_server=_convert_unloadable(
            model, unloaded, "class_share_file_server", _as_optional_str
        ),
        home_share_file_server=_convert_unloadable(
            model, unloaded, "home_share_file_server", _as_optional_str
        ),
        udm_properties=_convert_unloadable(model, unloaded, "udm_properties", _as_udm_properties),
    )
    if cache is None or not memoize:
        return school
    # Hand out a copy and keep the pristine one: returning the cached object
    # itself would let a caller's change to it leak into every later copy.
    cache.schools[model] = school
    return _clone_school(school)


def to_role(
    model: RoleModel,
    cache: ConversionCache | None = None,
    *,
    memoize: bool = True,
) -> Role:
    if cache is not None and memoize and (cached := cache.roles.get(model)) is not None:
        return _clone_role(cached)
    unloaded = _unloaded_attributes(model)
    role = Role(
        public_id=model.public_id,
        name=_convert_unloadable(model, unloaded, "name", _as_str),
        display_name=_convert_unloadable(model, unloaded, "display_name", _as_role_display_name),
    )
    if cache is None or not memoize:
        return role
    cache.roles[model] = role
    return _clone_role(role)


def to_group(
    model: GroupModel,
    cache: ConversionCache | None = None,
    *,
    memoize: bool = True,
) -> Group:
    if cache is not None and memoize and (cached := cache.groups.get(model)) is not None:
        return _clone_group(cached)
    unloaded = _unloaded_attributes(model)
    school: School | UnloadedType = UNLOADED
    if "school" not in unloaded:
        school = to_school(model.school, cache)

    roles: set[Role] | UnloadedType = UNLOADED
    if "roles" not in unloaded:
        roles = {to_role(r, cache) for r in model.roles}

    allowed_email_senders_users: set[User] | UnloadedType = UNLOADED
    if "allowed_email_senders_users" not in unloaded:
        allowed_email_senders_users = {
            _to_related_user(user) for user in model.allowed_email_senders_users
        }

    allowed_email_senders_groups: set[Group] | UnloadedType = UNLOADED
    if "allowed_email_senders_groups" not in unloaded:
        allowed_email_senders_groups = {
            to_group(group, cache) for group in model.allowed_email_senders_groups
        }

    members: set[User] | UnloadedType = UNLOADED
    if "members" not in unloaded:
        members = {_to_related_user(membership.user) for membership in model.members}

    member_roles: set[Role] | UnloadedType = UNLOADED
    if "member_roles" not in unloaded:
        member_roles = {to_role(role, cache) for role in model.member_roles}

    group = Group(
        public_id=model.public_id,
        record_uid=_convert_unloadable(model, unloaded, "record_uid", _as_str),
        source_uid=_convert_unloadable(model, unloaded, "source_uid", _as_str),
        name=_convert_unloadable(model, unloaded, "name", _as_str),
        display_name=_convert_unloadable(model, unloaded, "display_name", _as_str),
        create_share=_convert_unloadable(model, unloaded, "has_share", _as_bool),
        roles=roles,
        email=_convert_unloadable(model, unloaded, "email", _as_optional_str),
        allowed_email_senders_users=allowed_email_senders_users,
        allowed_email_senders_groups=allowed_email_senders_groups,
        members=members,
        member_roles=member_roles,
        school=school,
        description=_convert_unloadable(model, unloaded, "description", _as_optional_str),
        udm_properties=_convert_unloadable(model, unloaded, "udm_properties", _as_udm_properties),
    )
    if cache is None or not memoize:
        return group
    cache.groups[model] = group
    return _clone_group(group)


def _to_school_membership(model: SchoolMembershipModel, cache: ConversionCache) -> SchoolMembership:
    return SchoolMembership(
        school=to_school(model.school, cache),
        is_primary=model.is_primary,
        roles={to_role(role, cache) for role in model.roles},
        groups={to_group(group, cache) for group in model.groups},
    )


def _to_related_user(model: UserModel) -> User:
    unloaded = _unloaded_attributes(model)
    return User(
        public_id=model.public_id,
        record_uid=_convert_unloadable(model, unloaded, "record_uid", _as_str),
        source_uid=_convert_unloadable(model, unloaded, "source_uid", _as_str),
        name=_convert_unloadable(model, unloaded, "name", _as_str),
        firstname=_convert_unloadable(model, unloaded, "firstname", _as_str),
        lastname=_convert_unloadable(model, unloaded, "lastname", _as_str),
        email=_convert_unloadable(model, unloaded, "email", _as_optional_str),
        birthday=_convert_unloadable(model, unloaded, "birthday", _as_optional_date),
        expiration_date=_convert_unloadable(model, unloaded, "expiration_date", _as_optional_date),
        active=_convert_unloadable(model, unloaded, "active", _as_bool),
        school_memberships=UNLOADED,
        legal_wards=UNLOADED,
        legal_guardians=UNLOADED,
    )


def _optional_user_relation(models: tuple[UserModel, ...] | list[UserModel]) -> set[User]:
    return {_to_related_user(model) for model in models}


def to_user(model: UserModel, cache: ConversionCache | None = None) -> User:
    if cache is None:
        cache = ConversionCache()
    unloaded = _unloaded_attributes(model)
    school_memberships: dict[UUID, SchoolMembership] | UnloadedType = UNLOADED

    if "school_memberships" not in unloaded:
        school_memberships = {}
        for membership in (_to_school_membership(m, cache) for m in model.school_memberships):
            school_public_id = membership.school.public_id
            if not isinstance(school_public_id, UUID):
                raise ValueError("Mapped school membership has no UUID school public_id.")
            school_memberships[school_public_id] = membership

    legal_wards: set[User] | UnloadedType = UNLOADED
    if "legal_wards" not in unloaded:
        legal_wards = _optional_user_relation(model.legal_wards)

    legal_guardians: set[User] | UnloadedType = UNLOADED
    if "legal_guardians" not in unloaded:
        legal_guardians = _optional_user_relation(model.legal_guardians)

    return User(
        public_id=model.public_id,
        record_uid=_convert_unloadable(model, unloaded, "record_uid", _as_str),
        source_uid=_convert_unloadable(model, unloaded, "source_uid", _as_str),
        name=_convert_unloadable(model, unloaded, "name", _as_str),
        firstname=_convert_unloadable(model, unloaded, "firstname", _as_str),
        lastname=_convert_unloadable(model, unloaded, "lastname", _as_str),
        email=_convert_unloadable(model, unloaded, "email", _as_optional_str),
        birthday=_convert_unloadable(model, unloaded, "birthday", _as_optional_date),
        expiration_date=_convert_unloadable(model, unloaded, "expiration_date", _as_optional_date),
        active=_convert_unloadable(model, unloaded, "active", _as_bool),
        school_memberships=school_memberships,
        legal_wards=legal_wards,
        legal_guardians=legal_guardians,
        udm_properties=_convert_unloadable(model, unloaded, "udm_properties", _as_udm_properties),
    )


def school_from_patch(patched: PatchDict, public_id: UUID) -> School:
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


def group_from_patch(patched: PatchDict, public_id: UUID) -> Group:
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


def user_from_patch(patched: PatchDict, public_id: UUID) -> User:
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
