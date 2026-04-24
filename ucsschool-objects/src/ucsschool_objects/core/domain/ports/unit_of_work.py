"""Storage session port definitions for manager access and scope lifecycles."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self

from ucsschool_objects.core.domain.models import Group, Role, School, User

from .manager import Manager


class KelvinStorageSession(Protocol):
    """Abstract manager scope that may be transactional or plain session-scoped."""

    @property
    def schools(self) -> Manager[School]:  # pragma: no cover
        """Manager for School objects bound to this transaction scope."""

        ...

    @property
    def roles(self) -> Manager[Role]:  # pragma: no cover
        """Manager for Role objects bound to this transaction scope."""

        ...

    @property
    def groups(self) -> Manager[Group]:  # pragma: no cover
        """Manager for Group objects bound to this transaction scope."""

        ...

    @property
    def users(self) -> Manager[User]:  # pragma: no cover
        """Manager for User objects bound to this transaction scope."""

        ...

    async def __aenter__(self) -> Self:  # pragma: no cover
        """Open transactional resources."""

        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:  # pragma: no cover
        """Close resources and auto-commit/rollback depending on exception state."""

        ...


class KelvinStorageSessionFactory(Protocol):
    """Factory port that provides transactional and non-transactional storage scopes."""

    def transaction_scope(self) -> KelvinStorageSession:  # pragma: no cover
        """Return a scope with automatic transaction begin/commit/rollback semantics."""

        ...

    def session_scope(self) -> KelvinStorageSession:  # pragma: no cover
        """Return a scope without explicit transaction begin around the full context."""

        ...
