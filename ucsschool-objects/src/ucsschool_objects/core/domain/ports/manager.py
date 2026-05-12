"""Port definitions for domain object retrieval and mutation.

This module exposes protocol contracts that concrete adapters implement
to provide read/write access to domain objects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, Required, TypeAlias, TypedDict, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from uuid import UUID

    from ucsschool_objects.core.domain.load_spec import LoadSpec
    from ucsschool_objects.core.domain.query import SearchQuery, SortSpec

ManagerT = TypeVar("ManagerT")

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class JSONPathValueOperation(TypedDict):
    """RFC 6902 operation variant that carries a value payload."""

    op: Required[Literal["add", "replace", "set", "append", "merge"]]
    path: Required[str]
    value: Required[JSONValue]


class JSONPathRemoveOperation(TypedDict):
    """RFC 6902 operation variant that removes a node."""

    op: Required[Literal["remove"]]
    path: Required[str]


JSONPathOperation: TypeAlias = JSONPathValueOperation | JSONPathRemoveOperation


class Manager(Protocol[ManagerT]):
    """Abstract contract for retrieving and mutating domain objects."""

    async def get(
        self, public_id: UUID, *, load: LoadSpec | None = None
    ) -> ManagerT:  # pragma: no cover
        """Return a single object identified by its public UUID.

        Args:
            public_id: Public identifier of the object to fetch.
            load: Optional attribute/loading specification for eager loading.
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
    ) -> Iterable[ManagerT]:  # pragma: no cover
        """Search objects matching query and pagination/sorting criteria.

        The returned iterable may be lazy. Concrete implementations can defer
        mapping until iteration, so callers should consume the iterable while
        any required backing resources are still alive.

        Args:
            query: Optional structured filter expression.
            sort_by: Sort fields and direction.
            limit: Maximum number of records to return.
            offset: Number of matching records to skip.
            load: Optional attribute/loading specification for eager loading.
        """

        ...

    async def create(
        self,
        data: ManagerT,
    ) -> None:  # pragma: no cover
        """Create a new object from JSON-compatible input data.

        Args:
            data: A domain object that shall be created
        """

        ...

    async def modify(
        self,
        public_id: UUID,
        operations: Sequence[JSONPathOperation],
    ) -> None:  # pragma: no cover
        """Modify an existing object addressed by public UUID via JSONPath ops.

        Args:
            public_id: Public identifier of the object to modify.
            operations: Ordered JSONPath-based mutation operations.
        """

        ...

    async def delete(self, public_id: UUID) -> None:  # pragma: no cover
        """Delete an existing object identified by its public UUID.

        Args:
            public_id: Public identifier of the object to delete.
        """

        ...
