from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, TypeVar
from uuid import UUID

from ucsschool_objects.core.domain import Group, LoadSpec, School, SearchQuery, SortSpec, User

ReaderT = TypeVar("ReaderT", School, Group, User, covariant=True)


class Reader(Protocol[ReaderT]):
    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> ReaderT:  # pragma: no cover
        ...

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: Sequence[SortSpec] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Iterable[ReaderT]:  # pragma: no cover
        ...
