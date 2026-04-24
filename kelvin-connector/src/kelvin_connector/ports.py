from typing import Protocol

from ucsschool_objects.core.domain.ports import KelvinStorageSessionFactory

from .models import GroupEvent, SchoolEvent, UserEvent


class SynchronizationManagerProtocol(Protocol):
    storage_factory: KelvinStorageSessionFactory

    async def handle_user_event(self, user_event: UserEvent) -> None:
        ...

    async def handle_group_event(self, group_event: GroupEvent) -> None:
        ...

    async def handle_school_event(self, school_event: SchoolEvent) -> None:
        ...
