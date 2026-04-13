from collections.abc import Awaitable, Callable
from typing import TypeAlias

from ucsschool_objects.database_models import (
    Group,
    GroupType,
    Role,
    School,
    SchoolMembership,
    User,
)

SchoolDataFactory: TypeAlias = Callable[[], dict[str, object]]
GroupDataFactory: TypeAlias = Callable[[], dict[str, object]]
UserDataFactory: TypeAlias = Callable[[], dict[str, object]]
RoleDataFactory: TypeAlias = Callable[[], dict[str, object]]
GroupTypeDataFactory: TypeAlias = Callable[[], dict[str, object]]

AsyncSchoolFactory: TypeAlias = Callable[..., Awaitable[School]]
AsyncGroupFactory: TypeAlias = Callable[..., Awaitable[Group]]
AsyncUserFactory: TypeAlias = Callable[..., Awaitable[User]]
AsyncRoleFactory: TypeAlias = Callable[..., Awaitable[Role]]
AsyncGroupTypeFactory: TypeAlias = Callable[..., Awaitable[GroupType]]
AsyncSchoolMembershipFactory: TypeAlias = Callable[..., Awaitable[SchoolMembership]]

ModelInstance: TypeAlias = Group | GroupType | Role | School | SchoolMembership | User
RecordSourceInstance: TypeAlias = Group | School | User

ModelFactory: TypeAlias = (
    AsyncSchoolFactory
    | AsyncGroupFactory
    | AsyncUserFactory
    | AsyncRoleFactory
    | AsyncGroupTypeFactory
    | AsyncSchoolMembershipFactory
)
RecordSourceFactory: TypeAlias = Callable[..., Awaitable[RecordSourceInstance]]
