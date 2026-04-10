from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from ucsschool_objects.core.domain import Group, LoadSpec, School, SearchQuery, SortSpec, User


class SchoolReader(Protocol):
    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> School | None:
        ...

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: Sequence[SortSpec] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Sequence[School]:
        ...


class GroupReader(Protocol):
    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> Group | None:
        ...

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: Sequence[SortSpec] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Sequence[Group]:
        ...


class UserReader(Protocol):
    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> User | None:
        ...

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: Sequence[SortSpec] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Sequence[User]:
        ...
