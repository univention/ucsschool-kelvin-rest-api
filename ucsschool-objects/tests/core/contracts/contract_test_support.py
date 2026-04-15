from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, TypeAlias
from uuid import UUID

from ucsschool_objects.core.domain import LoadSpec, SearchQuery, SortSpec

if TYPE_CHECKING:
    from tests.test_types import (
        AsyncGroupFactory,
        AsyncGroupTypeFactory,
        AsyncRoleFactory,
        AsyncSchoolFactory,
        AsyncUserFactory,
    )


@dataclass(frozen=True)
class ReaderSearchExpectation:
    public_id: UUID
    expected_name: str
    query: SearchQuery


@dataclass(frozen=True)
class QueryExpectation:
    query: SearchQuery
    expected_names: tuple[str, ...]
    sort_by: tuple[SortSpec, ...] = field(default_factory=lambda: (SortSpec(field="name"),))


@dataclass(frozen=True)
class ReaderContractFactories:
    school_factory: AsyncSchoolFactory
    group_factory: AsyncGroupFactory
    group_type_factory: AsyncGroupTypeFactory
    role_factory: AsyncRoleFactory
    user_factory: AsyncUserFactory


@dataclass(frozen=True)
class SchoolQueryFactories:
    school_factory: AsyncSchoolFactory


@dataclass(frozen=True)
class GroupQueryFactories:
    school_factory: AsyncSchoolFactory
    group_factory: AsyncGroupFactory
    group_type_factory: AsyncGroupTypeFactory


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


class ReaderProtocol(Protocol):
    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> NamedRecord:
        ...

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: tuple[SortSpec, ...] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Iterable[NamedRecord]:
        ...


class SearchReaderProtocol(Protocol):
    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: tuple[SortSpec, ...] = (),
        limit: int = 50,
        offset: int = 0,
        load: object | None = None,
    ) -> Iterable[SearchNamedRecord]:
        ...


ReaderSetup: TypeAlias = Callable[[ReaderContractFactories], Awaitable[ReaderSearchExpectation]]
SchoolQuerySetup: TypeAlias = Callable[[SchoolQueryFactories], Awaitable[QueryExpectation]]
GroupQuerySetup: TypeAlias = Callable[[GroupQueryFactories], Awaitable[QueryExpectation]]
RoleQuerySetup: TypeAlias = Callable[[RoleQueryFactories], Awaitable[QueryExpectation]]
UserQuerySetup: TypeAlias = Callable[[UserQueryFactories], Awaitable[QueryExpectation]]
