from typing import Callable, Protocol

from ucsschool_objects.core.domain.ports import KelvinStorageSession, KelvinStorageSessionFactory

from .models import (
    GroupCreateEvent,
    GroupDeleteEvent,
    GroupModifyEvent,
    SchoolCreateEvent,
    SchoolDeleteEvent,
    SchoolModifyEvent,
    UserCreateEvent,
    UserDeleteEvent,
    UserModifyEvent,
)
from .nubus_compat import DNIDMapper

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
