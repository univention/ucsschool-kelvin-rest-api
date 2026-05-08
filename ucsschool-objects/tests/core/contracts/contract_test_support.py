from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, TypeAlias
from uuid import UUID

from ucsschool_objects.core.domain import SearchQuery, SortSpec

if TYPE_CHECKING:
    from tests.test_types import (
        AsyncGroupFactory,
        AsyncGroupTypeFactory,
        AsyncRoleFactory,
        AsyncSchoolFactory,
        AsyncUserFactory,
    )


@dataclass(frozen=True)
class ManagerSearchExpectation:
    public_id: UUID
    expected_name: str
    query: SearchQuery


@dataclass(frozen=True)
class QueryExpectation:
    query: SearchQuery
    expected_names: tuple[str, ...]
    sort_by: tuple[SortSpec, ...] = field(default_factory=lambda: (SortSpec(field="name"),))


@dataclass(frozen=True)
class ManagerContractFactories:
    school_factory: AsyncSchoolFactory
    group_factory: AsyncGroupFactory
    roles_factory: AsyncGroupTypeFactory
    role_factory: AsyncRoleFactory
    user_factory: AsyncUserFactory


@dataclass(frozen=True)
class SchoolQueryFactories:
    school_factory: AsyncSchoolFactory


@dataclass(frozen=True)
class GroupQueryFactories:
    school_factory: AsyncSchoolFactory
    group_factory: AsyncGroupFactory
    roles_factory: AsyncGroupTypeFactory


@dataclass(frozen=True)
class RoleQueryFactories:
    role_factory: AsyncRoleFactory


@dataclass(frozen=True)
class UserQueryFactories:
    user_factory: AsyncUserFactory


class NamedRecord(Protocol):
    name: str
    public_id: UUID


class SearchNamedRecord(Protocol):
    name: str


ManagerSetup: TypeAlias = Callable[[ManagerContractFactories], Awaitable[ManagerSearchExpectation]]
SchoolQuerySetup: TypeAlias = Callable[[SchoolQueryFactories], Awaitable[QueryExpectation]]
GroupQuerySetup: TypeAlias = Callable[[GroupQueryFactories], Awaitable[QueryExpectation]]
RoleQuerySetup: TypeAlias = Callable[[RoleQueryFactories], Awaitable[QueryExpectation]]
UserQuerySetup: TypeAlias = Callable[[UserQueryFactories], Awaitable[QueryExpectation]]
