# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from collections.abc import Coroutine
from typing import Any, Callable, Protocol, TypeVar

from ucsschool_objects import DNIDMapper, KelvinStorageSession, KelvinStorageSessionFactory

from .models import (
    GroupCreateEvent,
    GroupDeleteEvent,
    GroupModifyEvent,
    HostGroupCreateEvent,
    HostGroupDeleteEvent,
    HostGroupModifyEvent,
    SchoolCreateEvent,
    SchoolDeleteEvent,
    SchoolModifyEvent,
    UserCreateEvent,
    UserDeleteEvent,
    UserModifyEvent,
)

DNIDMapperFactory = Callable[[KelvinStorageSession], DNIDMapper]


class SynchronizationManagerProtocol(Protocol):  # pragma: no cover
    storage_factory: KelvinStorageSessionFactory

    async def handle_user_create(self, event: UserCreateEvent) -> None: ...

    async def handle_user_modify(self, event: UserModifyEvent) -> None: ...

    async def handle_user_delete(self, event: UserDeleteEvent) -> None: ...

    async def handle_group_create(self, event: GroupCreateEvent) -> None: ...

    async def handle_group_modify(self, event: GroupModifyEvent) -> None: ...

    async def handle_group_delete(self, event: GroupDeleteEvent) -> None: ...

    async def handle_school_create(self, event: SchoolCreateEvent) -> None: ...

    async def handle_school_modify(self, event: SchoolModifyEvent) -> None: ...

    async def handle_school_delete(self, event: SchoolDeleteEvent) -> None: ...

    async def handle_host_group_create(self, event: HostGroupCreateEvent) -> None: ...

    async def handle_host_group_modify(self, event: HostGroupModifyEvent) -> None: ...

    async def handle_host_group_delete(self, event: HostGroupDeleteEvent) -> None: ...


T = TypeVar("T")


class CoroutineRunnerProtocol(Protocol):  # pragma: no cover
    def run(self, coro: Coroutine[Any, Any, T], timeout: float | None = None) -> T: ...
