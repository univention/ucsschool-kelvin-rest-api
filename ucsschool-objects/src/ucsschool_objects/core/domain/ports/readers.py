"""Read-side port definitions for domain object retrieval.

This module exposes protocol contracts that concrete adapters implement
to provide read access to domain objects.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, TypeVar
from uuid import UUID

from ucsschool_objects.core.domain.load_spec import LoadSpec
from ucsschool_objects.core.domain.query import SearchQuery, SortSpec

ReaderT = TypeVar("ReaderT", covariant=True)


class Reader(Protocol[ReaderT]):
    """Abstract read contract for retrieving and listing domain objects."""

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> ReaderT:  # pragma: no cover
        """Return a single object identified by its public UUID.

        Args:
            public_id: Public identifier of the object to fetch.
            load: Optional relation/loading specification for eager loading.
        """

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
        """Search objects matching query and pagination/sorting criteria.

        The returned iterable may be lazy. Concrete implementations can defer
        mapping until iteration, so callers should consume the iterable while
        any required backing resources are still alive.

        Args:
            query: Optional structured filter expression.
            sort_by: Sort fields and direction.
            limit: Maximum number of records to return.
            offset: Number of matching records to skip.
            load: Optional relation/loading specification for eager loading.
        """

        ...
