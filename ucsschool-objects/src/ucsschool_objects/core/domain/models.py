from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date
    from uuid import UUID


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


@dataclass(eq=False)
class School:
    record_uid: str | UnloadedType
    source_uid: str | UnloadedType
    name: str | UnloadedType
    display_name: str | UnloadedType
    educational_servers: set[str] | UnloadedType
    administrative_servers: set[str] | UnloadedType
    public_id: UUID | UnsetType = UNSET
    class_share_file_server: str | None | UnloadedType = None
    home_share_file_server: str | None | UnloadedType = None

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, School):
            return NotImplemented
        return self.public_id == other.public_id

    @classmethod
    def minimal(cls, public_id: UUID) -> School:
        unloaded = UnloadedType()
        return cls(
            public_id=public_id,
            record_uid=unloaded,
            source_uid=unloaded,
            name=unloaded,
            display_name=unloaded,
            educational_servers=unloaded,
            administrative_servers=unloaded,
            class_share_file_server=unloaded,
            home_share_file_server=unloaded,
        )


@dataclass(frozen=True, eq=False)
class Role:
    name: str | UnloadedType
    display_name: dict[str, str] | UnloadedType
    public_id: UUID | UnsetType = UNSET

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return self.public_id == other.public_id

    @classmethod
    def minimal(cls, public_id: UUID) -> Role:
        unloaded = UnloadedType()
        return cls(
            public_id=public_id,
            name=unloaded,
            display_name=unloaded,
        )


@dataclass(eq=False)
class Group:
    record_uid: str | UnloadedType
    source_uid: str | UnloadedType
    name: str | UnloadedType
    display_name: str | UnloadedType
    create_share: bool | UnloadedType
    roles: set[Role] | UnloadedType
    allowed_email_senders_users: set[User] | UnloadedType
    allowed_email_senders_groups: set[Group] | UnloadedType
    members: set[User] | UnloadedType
    member_roles: set[Role] | UnloadedType
    school: School | UnloadedType
    public_id: UUID | UnsetType = UNSET
    email: str | None | UnloadedType = None

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Group):
            return NotImplemented
        return self.public_id == other.public_id

    @classmethod
    def minimal(cls, public_id: UUID) -> Group:
        unloaded = UnloadedType()
        return cls(
            public_id=public_id,
            record_uid=unloaded,
            source_uid=unloaded,
            name=unloaded,
            display_name=unloaded,
            create_share=unloaded,
            roles=unloaded,
            allowed_email_senders_users=unloaded,
            allowed_email_senders_groups=unloaded,
            members=unloaded,
            member_roles=unloaded,
            school=unloaded,
            email=unloaded,
        )


@dataclass(eq=False)
class SchoolMembership:
    school: School
    is_primary: bool
    roles: set[Role]
    groups: set[Group]

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


@dataclass(eq=False)
class User:
    record_uid: str | UnloadedType
    source_uid: str | UnloadedType
    name: str | UnloadedType
    firstname: str | UnloadedType
    lastname: str | UnloadedType
    active: bool | UnloadedType
    school_memberships: dict[UUID, SchoolMembership] | UnloadedType
    legal_wards: set[User] | UnloadedType = field(default_factory=set)
    legal_guardians: set[User] | UnloadedType = field(default_factory=set)
    public_id: UUID | UnsetType = UNSET
    email: str | None | UnloadedType = None
    birthday: date | None | UnloadedType = None
    expiration_date: date | None | UnloadedType = None

    def __hash__(self) -> int:
        return hash(self.public_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):
            return NotImplemented
        return self.public_id == other.public_id

    @classmethod
    def minimal(cls, public_id: UUID) -> User:
        unloaded = UnloadedType()
        return cls(
            public_id=public_id,
            record_uid=unloaded,
            source_uid=unloaded,
            name=unloaded,
            firstname=unloaded,
            lastname=unloaded,
            active=unloaded,
            school_memberships=unloaded,
            legal_guardians=unloaded,
            legal_wards=unloaded,
        )

    @property
    def primary_school(self) -> School | UnloadedType:
        if isinstance(self.school_memberships, UnloadedType):
            return UNLOADED
        for membership in self.school_memberships.values():
            if membership.is_primary:
                return membership.school
        raise ValueError("User has no primary school membership.")

    @property
    def groups(self) -> set[Group] | UnloadedType:
        if isinstance(self.school_memberships, UnloadedType):
            return UNLOADED
        result: set[Group] = set()
        for membership in self.school_memberships.values():
            result.update(membership.groups)
        return result

    @property
    def roles(self) -> set[Role] | UnloadedType:
        if isinstance(self.school_memberships, UnloadedType):
            return UNLOADED
        result: set[Role] = set()
        for membership in self.school_memberships.values():
            result.update(membership.roles)
        return result
