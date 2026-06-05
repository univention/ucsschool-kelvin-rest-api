from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, TypeAlias, TypeVar, cast

if TYPE_CHECKING:
    from datetime import date
    from uuid import UUID

TLoaded = TypeVar("TLoaded")


@dataclass(frozen=True)
class UnloadedType:
    """Sentinel value for intentionally unloaded relationships."""


@dataclass(frozen=True)
class UnsetType:
    """
    Sentinel value for intentionally unset attributes (like public_id
    for new/unstored objects).
    """


UNLOADED = UnloadedType()
UNSET = UnsetType()


def _require_loaded(
    value: TLoaded | UnloadedType,
    *,
    object_type: str,
    field_name: str,
) -> TLoaded:
    if isinstance(value, UnloadedType):
        raise ValueError(f"{object_type}.{field_name} is not loaded.")
    return value


def is_loaded(instance: object, field_name: str) -> bool:
    private_field_name = f"_{field_name}"
    if not hasattr(instance, private_field_name):
        raise AttributeError(f"{type(instance).__name__} has no attribute {field_name!r}.")

    field_value = cast(object, getattr(instance, private_field_name))
    return not isinstance(field_value, UnloadedType)


class School:
    __serialize_fields__ = (
        "public_id",
        "_record_uid",
        "_source_uid",
        "_name",
        "_display_name",
        "_educational_servers",
        "_administrative_servers",
        "_class_share_file_server",
        "_home_share_file_server",
    )

    def __init__(
        self,
        public_id: UUID | UnsetType = UNSET,
        record_uid: str | UnloadedType = UNLOADED,
        source_uid: str | UnloadedType = UNLOADED,
        name: str | UnloadedType = UNLOADED,
        display_name: str | UnloadedType = UNLOADED,
        educational_servers: set[str] | UnloadedType = UNLOADED,
        administrative_servers: set[str] | UnloadedType = UNLOADED,
        class_share_file_server: str | None | UnloadedType = UNLOADED,
        home_share_file_server: str | None | UnloadedType = UNLOADED,
    ) -> None:
        self.public_id = public_id
        self._record_uid = record_uid
        self._source_uid = source_uid
        self._name = name
        self._display_name = display_name
        self._educational_servers = educational_servers
        self._administrative_servers = administrative_servers
        self._class_share_file_server = class_share_file_server
        self._home_share_file_server = home_share_file_server

    @classmethod
    def minimal(cls, public_id: UUID) -> School:
        return cls(
            public_id=public_id,
        )

    @property
    def record_uid(self) -> str:
        return _require_loaded(self._record_uid, object_type="School", field_name="record_uid")

    @record_uid.setter
    def record_uid(self, value: str) -> None:
        self._record_uid = value

    @property
    def source_uid(self) -> str:
        return _require_loaded(self._source_uid, object_type="School", field_name="source_uid")

    @source_uid.setter
    def source_uid(self, value: str) -> None:
        self._source_uid = value

    @property
    def name(self) -> str:
        return _require_loaded(self._name, object_type="School", field_name="name")

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    @property
    def display_name(self) -> str:
        return _require_loaded(self._display_name, object_type="School", field_name="display_name")

    @display_name.setter
    def display_name(self, value: str) -> None:
        self._display_name = value

    @property
    def educational_servers(self) -> set[str]:
        return _require_loaded(
            self._educational_servers,
            object_type="School",
            field_name="educational_servers",
        )

    @educational_servers.setter
    def educational_servers(self, value: set[str]) -> None:
        self._educational_servers = value

    @property
    def administrative_servers(self) -> set[str]:
        return _require_loaded(
            self._administrative_servers,
            object_type="School",
            field_name="administrative_servers",
        )

    @administrative_servers.setter
    def administrative_servers(self, value: set[str]) -> None:
        self._administrative_servers = value

    @property
    def class_share_file_server(self) -> str | None:
        return _require_loaded(
            self._class_share_file_server,
            object_type="School",
            field_name="class_share_file_server",
        )

    @class_share_file_server.setter
    def class_share_file_server(self, value: str | None) -> None:
        self._class_share_file_server = value

    @property
    def home_share_file_server(self) -> str | None:
        return _require_loaded(
            self._home_share_file_server,
            object_type="School",
            field_name="home_share_file_server",
        )

    @home_share_file_server.setter
    def home_share_file_server(self, value: str | None) -> None:
        self._home_share_file_server = value

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, School):
            return NotImplemented
        return self.public_id == other.public_id


class Role:
    __serialize_fields__ = (
        "public_id",
        "_name",
        "_display_name",
    )

    def __init__(
        self,
        public_id: UUID | UnsetType = UNSET,
        name: str | UnloadedType = UNLOADED,
        display_name: dict[str, str] | UnloadedType = UNLOADED,
    ) -> None:
        self.public_id = public_id
        self._name = name
        self._display_name = display_name

    @classmethod
    def minimal(cls, public_id: UUID) -> Role:
        return cls(
            public_id=public_id,
        )

    @property
    def name(self) -> str:
        return _require_loaded(self._name, object_type="Role", field_name="name")

    @property
    def display_name(self) -> dict[str, str]:
        return _require_loaded(self._display_name, object_type="Role", field_name="display_name")

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return self.public_id == other.public_id


class Group:
    __serialize_fields__ = (
        "public_id",
        "_record_uid",
        "_source_uid",
        "_name",
        "_display_name",
        "_create_share",
        "_roles",
        "_allowed_email_senders_users",
        "_allowed_email_senders_groups",
        "_members",
        "_member_roles",
        "_school",
        "_email",
    )

    def __init__(
        self,
        public_id: UUID | UnsetType = UNSET,
        record_uid: str | UnloadedType = UNLOADED,
        source_uid: str | UnloadedType = UNLOADED,
        name: str | UnloadedType = UNLOADED,
        display_name: str | UnloadedType = UNLOADED,
        create_share: bool | UnloadedType = UNLOADED,
        roles: set[Role] | UnloadedType = UNLOADED,
        allowed_email_senders_users: set[User] | UnloadedType = UNLOADED,
        allowed_email_senders_groups: set[Group] | UnloadedType = UNLOADED,
        members: set[User] | UnloadedType = UNLOADED,
        member_roles: set[Role] | UnloadedType = UNLOADED,
        school: School | UnloadedType = UNLOADED,
        email: str | None | UnloadedType = UNLOADED,
    ) -> None:
        self.public_id = public_id
        self._record_uid = record_uid
        self._source_uid = source_uid
        self._name = name
        self._display_name = display_name
        self._create_share = create_share
        self._roles = roles
        self._allowed_email_senders_users = allowed_email_senders_users
        self._allowed_email_senders_groups = allowed_email_senders_groups
        self._members = members
        self._member_roles = member_roles
        self._school = school
        self._email = email

    @classmethod
    def minimal(cls, public_id: UUID) -> Group:
        return cls(
            public_id=public_id,
        )

    @property
    def record_uid(self) -> str:
        return _require_loaded(self._record_uid, object_type="Group", field_name="record_uid")

    @record_uid.setter
    def record_uid(self, value: str) -> None:
        self._record_uid = value

    @property
    def source_uid(self) -> str:
        return _require_loaded(self._source_uid, object_type="Group", field_name="source_uid")

    @source_uid.setter
    def source_uid(self, value: str) -> None:
        self._source_uid = value

    @property
    def name(self) -> str:
        return _require_loaded(self._name, object_type="Group", field_name="name")

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    @property
    def display_name(self) -> str:
        return _require_loaded(self._display_name, object_type="Group", field_name="display_name")

    @display_name.setter
    def display_name(self, value: str) -> None:
        self._display_name = value

    @property
    def create_share(self) -> bool:
        return _require_loaded(self._create_share, object_type="Group", field_name="create_share")

    @create_share.setter
    def create_share(self, value: bool) -> None:
        self._create_share = value

    @property
    def roles(self) -> set[Role]:
        return _require_loaded(self._roles, object_type="Group", field_name="roles")

    @roles.setter
    def roles(self, value: set[Role]) -> None:
        self._roles = value

    @property
    def allowed_email_senders_users(self) -> set[User]:
        return _require_loaded(
            self._allowed_email_senders_users,
            object_type="Group",
            field_name="allowed_email_senders_users",
        )

    @allowed_email_senders_users.setter
    def allowed_email_senders_users(self, value: set[User]) -> None:
        self._allowed_email_senders_users = value

    @property
    def allowed_email_senders_groups(self) -> set[Group]:
        return _require_loaded(
            self._allowed_email_senders_groups,
            object_type="Group",
            field_name="allowed_email_senders_groups",
        )

    @allowed_email_senders_groups.setter
    def allowed_email_senders_groups(self, value: set[Group]) -> None:
        self._allowed_email_senders_groups = value

    @property
    def members(self) -> set[User]:
        return _require_loaded(self._members, object_type="Group", field_name="members")

    @members.setter
    def members(self, value: set[User]) -> None:
        self._members = value

    @property
    def member_roles(self) -> set[Role]:
        return _require_loaded(
            self._member_roles,
            object_type="Group",
            field_name="member_roles",
        )

    @member_roles.setter
    def member_roles(self, value: set[Role]) -> None:
        self._member_roles = value

    @property
    def school(self) -> School:
        return _require_loaded(self._school, object_type="Group", field_name="school")

    @school.setter
    def school(self, value: School) -> None:
        self._school = value

    @property
    def email(self) -> str | None:
        return _require_loaded(self._email, object_type="Group", field_name="email")

    @email.setter
    def email(self, value: str | None) -> None:
        self._email = value

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Group):
            return NotImplemented
        return self.public_id == other.public_id


class SchoolMembership:
    __serialize_fields__ = (
        "school",
        "is_primary",
        "roles",
        "groups",
    )

    def __init__(
        self,
        school: School,
        is_primary: bool,
        roles: set[Role],
        groups: set[Group],
    ) -> None:
        self.school = school
        self.is_primary = is_primary
        self.roles = roles
        self.groups = groups

    def __hash__(self) -> int:
        # Roles/groups are mutable sets on the model, so normalize for hashing.
        return hash((self.school, self.is_primary, frozenset(self.roles), frozenset(self.groups)))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SchoolMembership):
            return NotImplemented
        return (
            self.school,
            self.is_primary,
            self.roles,
            self.groups,
        ) == (
            other.school,
            other.is_primary,
            other.roles,
            other.groups,
        )


class User:
    __serialize_fields__ = (
        "public_id",
        "_record_uid",
        "_source_uid",
        "_name",
        "_firstname",
        "_lastname",
        "_active",
        "_school_memberships",
        "_legal_wards",
        "_legal_guardians",
        "_email",
        "_birthday",
        "_expiration_date",
    )

    def __init__(
        self,
        record_uid: str | UnloadedType,
        source_uid: str | UnloadedType,
        name: str | UnloadedType,
        firstname: str | UnloadedType,
        lastname: str | UnloadedType,
        active: bool | UnloadedType,
        school_memberships: dict[UUID, SchoolMembership] | UnloadedType,
        legal_wards: set[User] | UnloadedType,
        legal_guardians: set[User] | UnloadedType,
        public_id: UUID | UnsetType = UNSET,
        email: str | None | UnloadedType = None,
        birthday: date | None | UnloadedType = None,
        expiration_date: date | None | UnloadedType = None,
    ) -> None:
        self.public_id = public_id
        self._record_uid = record_uid
        self._source_uid = source_uid
        self._name = name
        self._firstname = firstname
        self._lastname = lastname
        self._active = active
        self._school_memberships = school_memberships
        self._legal_wards = legal_wards
        self._legal_guardians = legal_guardians
        self._email = email
        self._birthday = birthday
        self._expiration_date = expiration_date

    @property
    def record_uid(self) -> str:
        return _require_loaded(self._record_uid, object_type="User", field_name="record_uid")

    @record_uid.setter
    def record_uid(self, value: str) -> None:
        self._record_uid = value

    @property
    def source_uid(self) -> str:
        return _require_loaded(self._source_uid, object_type="User", field_name="source_uid")

    @source_uid.setter
    def source_uid(self, value: str) -> None:
        self._source_uid = value

    @property
    def name(self) -> str:
        return _require_loaded(self._name, object_type="User", field_name="name")

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    @property
    def firstname(self) -> str:
        return _require_loaded(self._firstname, object_type="User", field_name="firstname")

    @firstname.setter
    def firstname(self, value: str) -> None:
        self._firstname = value

    @property
    def lastname(self) -> str:
        return _require_loaded(self._lastname, object_type="User", field_name="lastname")

    @lastname.setter
    def lastname(self, value: str) -> None:
        self._lastname = value

    @property
    def active(self) -> bool:
        return _require_loaded(self._active, object_type="User", field_name="active")

    @active.setter
    def active(self, value: bool) -> None:
        self._active = value

    @property
    def school_memberships(self) -> dict[UUID, SchoolMembership]:
        return _require_loaded(
            self._school_memberships,
            object_type="User",
            field_name="school_memberships",
        )

    @school_memberships.setter
    def school_memberships(self, value: dict[UUID, SchoolMembership]) -> None:
        self._school_memberships = value

    @property
    def legal_wards(self) -> set[User]:
        return _require_loaded(self._legal_wards, object_type="User", field_name="legal_wards")

    @legal_wards.setter
    def legal_wards(self, value: set[User]) -> None:
        self._legal_wards = value

    @property
    def legal_guardians(self) -> set[User]:
        return _require_loaded(
            self._legal_guardians,
            object_type="User",
            field_name="legal_guardians",
        )

    @legal_guardians.setter
    def legal_guardians(self, value: set[User]) -> None:
        self._legal_guardians = value

    @property
    def email(self) -> str | None:
        return _require_loaded(self._email, object_type="User", field_name="email")

    @email.setter
    def email(self, value: str | None) -> None:
        self._email = value

    @property
    def birthday(self) -> date | None:
        return _require_loaded(self._birthday, object_type="User", field_name="birthday")

    @birthday.setter
    def birthday(self, value: date | None) -> None:
        self._birthday = value

    @property
    def expiration_date(self) -> date | None:
        return _require_loaded(
            self._expiration_date,
            object_type="User",
            field_name="expiration_date",
        )

    @expiration_date.setter
    def expiration_date(self, value: date | None) -> None:
        self._expiration_date = value

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):
            return NotImplemented
        return self.public_id == other.public_id

    @classmethod
    def minimal(cls, public_id: UUID) -> User:
        return cls(
            public_id=public_id,
            record_uid=UNLOADED,
            source_uid=UNLOADED,
            name=UNLOADED,
            firstname=UNLOADED,
            lastname=UNLOADED,
            active=UNLOADED,
            school_memberships=UNLOADED,
            legal_guardians=UNLOADED,
            legal_wards=UNLOADED,
        )

    @property
    def primary_school(self) -> School:
        for membership in self.school_memberships.values():
            if membership.is_primary:
                return membership.school
        raise ValueError("User has no primary school membership.")

    @property
    def groups(self) -> set[Group]:
        result: set[Group] = set()
        for membership in self.school_memberships.values():
            result.update(membership.groups)
        return result

    @property
    def roles(self) -> set[Role]:
        result: set[Role] = set()
        for membership in self.school_memberships.values():
            result.update(membership.roles)
        return result


SerializableDomainObject: TypeAlias = School | Role | Group | SchoolMembership | User


def serialized_domain_field_name(field_name: str) -> str:
    """Map an internal domain field name to the public serialized field name."""
    return field_name[1:] if field_name.startswith("_") else field_name


def get_properties(
    domain_obj: SerializableDomainObject | type[SerializableDomainObject],
) -> set[str]:
    """Return all public property names for a domain object or domain model class."""
    return {serialized_domain_field_name(field_name) for field_name in domain_obj.__serialize_fields__}


def domain_object_properties(
    domain_obj: SerializableDomainObject,
    serialize_value: Callable[[object], object],
) -> dict[str, object]:
    """Return serialized properties for a domain object using __serialize_fields__."""
    return {
        serialized_domain_field_name(field_name): serialize_value(
            cast(object, getattr(domain_obj, field_name))
        )
        for field_name in domain_obj.__serialize_fields__
    }
