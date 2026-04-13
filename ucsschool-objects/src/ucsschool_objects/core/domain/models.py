from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import cached_property
from uuid import UUID


@dataclass(frozen=True)
class UnloadedType:
    """Sentinel value for intentionally unloaded relationships."""


UNLOADED = UnloadedType()


@dataclass(eq=False)
class School:
    public_id: UUID
    record_uid: str
    source_uid: str
    name: str
    display_name: dict[str, str]
    educational_servers: tuple[str, ...]
    administrative_servers: tuple[str, ...]
    class_share_file_server: str | None
    home_share_file_server: str | None

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, School):
            return NotImplemented
        return self.public_id == other.public_id


@dataclass(eq=False)
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


@dataclass(eq=False)
class Group:
    public_id: UUID
    record_uid: str
    source_uid: str
    name: str
    display_name: dict[str, str]
    create_share: bool
    group_type: str
    email: str | None = None
    allowed_email_senders_users: tuple[str, ...] | UnloadedType = UNLOADED
    allowed_email_senders_groups: tuple[str, ...] | UnloadedType = UNLOADED
    member_roles: tuple[Role, ...] | UnloadedType = UNLOADED
    school: School | UnloadedType = UNLOADED

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Group):
            return NotImplemented
        return self.public_id == other.public_id


@dataclass(eq=False)
class SchoolClass(Group):
    pass


@dataclass(eq=False)
class WorkGroup(Group):
    pass


@dataclass
class SchoolMembership:
    school: School | UnloadedType
    is_primary: bool
    roles: tuple[Role, ...] | UnloadedType = UNLOADED
    groups: tuple[Group, ...] | UnloadedType = UNLOADED


@dataclass(eq=False)
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
    school_memberships: tuple[SchoolMembership, ...] | UnloadedType = UNLOADED
    legal_wards: tuple["User", ...] | UnloadedType = UNLOADED
    legal_guardians: tuple["User", ...] | UnloadedType = UNLOADED

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):
            return NotImplemented
        return self.public_id == other.public_id

    @cached_property
    def primary_school(self) -> School | UnloadedType:
        if isinstance(self.school_memberships, UnloadedType):
            return UNLOADED
        for membership in self.school_memberships:
            if membership.is_primary:
                return membership.school
        raise ValueError("User has no primary school membership.")

    @cached_property
    def groups(self) -> tuple[Group, ...] | UnloadedType:
        if isinstance(self.school_memberships, UnloadedType):
            return UNLOADED
        by_public_id: dict[UUID, Group] = {}
        for membership in self.school_memberships:
            if isinstance(membership.groups, UnloadedType):
                return UNLOADED
            for group in membership.groups:
                by_public_id[group.public_id] = group
        return tuple(by_public_id.values())
