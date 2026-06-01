from typing import Callable, Protocol

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

    async def handle_user_create(self, event: UserCreateEvent) -> None:
        ...

    async def handle_user_modify(self, event: UserModifyEvent) -> None:
        ...

    async def handle_user_delete(self, event: UserDeleteEvent) -> None:
        ...

    async def handle_group_create(self, event: GroupCreateEvent) -> None:
        ...

    async def handle_group_modify(self, event: GroupModifyEvent) -> None:
        ...

    async def handle_group_delete(self, event: GroupDeleteEvent) -> None:
        ...

    async def handle_school_create(self, event: SchoolCreateEvent) -> None:
        ...

    async def handle_school_modify(self, event: SchoolModifyEvent) -> None:
        ...

    async def handle_school_delete(self, event: SchoolDeleteEvent) -> None:
        ...

    async def handle_host_group_create(self, event: HostGroupCreateEvent) -> None:
        ...

    async def handle_host_group_modify(self, event: HostGroupModifyEvent) -> None:
        ...

    async def handle_host_group_delete(self, event: HostGroupDeleteEvent) -> None:
        ...
