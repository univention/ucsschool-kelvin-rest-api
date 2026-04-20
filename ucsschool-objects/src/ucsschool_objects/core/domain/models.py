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
    record_uid: str | UnloadedType = UNLOADED
    source_uid: str | UnloadedType = UNLOADED
    name: str | UnloadedType = UNLOADED
    display_name: dict[str, str] | UnloadedType = UNLOADED
    educational_servers: frozenset[str] | UnloadedType = UNLOADED
    administrative_servers: frozenset[str] | UnloadedType = UNLOADED
    class_share_file_server: str | None | UnloadedType = UNLOADED
    home_share_file_server: str | None | UnloadedType = UNLOADED

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, School):
            return NotImplemented
        return self.public_id == other.public_id


@dataclass(frozen=True, eq=False)
class Role:
    public_id: UUID
    name: str | UnloadedType = UNLOADED
    display_name: dict[str, str] | UnloadedType = UNLOADED

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return self.public_id == other.public_id


@dataclass(frozen=True, eq=False)
class Group:
    public_id: UUID
    record_uid: str | UnloadedType = UNLOADED
    source_uid: str | UnloadedType = UNLOADED
    name: str | UnloadedType = UNLOADED
    display_name: dict[str, str] | UnloadedType = UNLOADED
    create_share: bool | UnloadedType = UNLOADED
    group_type: str | UnloadedType = UNLOADED
    email: str | None | UnloadedType = UNLOADED
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


@dataclass(frozen=True, eq=False)
class SchoolMembership:
    school: School
    is_primary: bool
    roles: frozenset[Role]
    groups: frozenset[Group]

    def __hash__(self) -> int:
        return hash((self.school, self.is_primary, self.roles, self.groups))

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


@dataclass(frozen=True, eq=False)
class User:
    public_id: UUID
    record_uid: str | UnloadedType = UNLOADED
    source_uid: str | UnloadedType = UNLOADED
    name: str | UnloadedType = UNLOADED
    firstname: str | UnloadedType = UNLOADED
    lastname: str | UnloadedType = UNLOADED
    email: str | None | UnloadedType = UNLOADED
    birthday: date | None | UnloadedType = UNLOADED
    expiration_date: date | None | UnloadedType = UNLOADED
    active: bool | UnloadedType = UNLOADED
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
            result.update(membership.groups)
        return frozenset(result)

    @property
    def roles(self) -> frozenset[Role] | UnloadedType:
        if isinstance(self.school_memberships, UnloadedType):
            return UNLOADED
        result: set[Role] = set()
        for membership in self.school_memberships:
            result.update(membership.roles)
        return frozenset(result)
