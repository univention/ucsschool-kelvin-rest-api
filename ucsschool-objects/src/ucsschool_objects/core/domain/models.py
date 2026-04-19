from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True)
class UnloadedType:
    """Sentinel value for intentionally unloaded relationships."""


UNLOADED = UnloadedType()


@dataclass(frozen=True, eq=False)
class School:
    public_id: UUID
    record_uid: str
    source_uid: str
    name: str
    display_name: dict[str, str]
    educational_servers: frozenset[str]
    administrative_servers: frozenset[str]
    class_share_file_server: str | None
    home_share_file_server: str | None

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, School):
            return NotImplemented
        return self.public_id == other.public_id


@dataclass(frozen=True, eq=False)
class Role:
    public_id: UUID
    name: str
    display_name: dict[str, str]

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return self.public_id == other.public_id


@dataclass(frozen=True, eq=False)
class Group:
    public_id: UUID
    record_uid: str
    source_uid: str
    name: str
    display_name: dict[str, str]
    create_share: bool
    group_type: str
    email: str | None = None
    allowed_email_senders_users: frozenset[str] | UnloadedType = UNLOADED
    allowed_email_senders_groups: frozenset[str] | UnloadedType = UNLOADED
    member_roles: frozenset[Role] | UnloadedType = UNLOADED
    school: School | UnloadedType = UNLOADED

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Group):
            return NotImplemented
        return self.public_id == other.public_id


@dataclass(frozen=True)
class SchoolMembership:
    school: School | UnloadedType
    is_primary: bool
    roles: frozenset[Role] | UnloadedType = UNLOADED
    groups: frozenset[Group] | UnloadedType = UNLOADED


@dataclass(frozen=True, eq=False)
class User:
    public_id: UUID
    record_uid: str
    source_uid: str
    name: str
    firstname: str
    lastname: str
    email: str | None
    birthday: date | None
    expiration_date: date | None
    active: bool
    school_memberships: frozenset[SchoolMembership] | UnloadedType = UNLOADED
    legal_wards: frozenset["User"] | UnloadedType = UNLOADED
    legal_guardians: frozenset["User"] | UnloadedType = UNLOADED

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):
            return NotImplemented
        return self.public_id == other.public_id

    @property
    def primary_school(self) -> School | UnloadedType:
        if isinstance(self.school_memberships, UnloadedType):
            return UNLOADED
        for membership in self.school_memberships:
            if membership.is_primary:
                return membership.school
        raise ValueError("User has no primary school membership.")

    @property
    def groups(self) -> frozenset[Group] | UnloadedType:
        if isinstance(self.school_memberships, UnloadedType):
            return UNLOADED
        result: set[Group] = set()
        for membership in self.school_memberships:
            if isinstance(membership.groups, UnloadedType):
                return UNLOADED
            result.update(membership.groups)
        return frozenset(result)

    @property
    def roles(self) -> frozenset[Role] | UnloadedType:
        if isinstance(self.school_memberships, UnloadedType):
            return UNLOADED
        result: set[Role] = set()
        for membership in self.school_memberships:
            if isinstance(membership.roles, UnloadedType):
                return UNLOADED
            result.update(membership.roles)
        return frozenset(result)
