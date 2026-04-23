from collections.abc import Callable
from typing import Any, Protocol

from ucsschool_objects.core.domain.models import Group, Role, School, User
from ucsschool_objects.core.domain.ports import Manager

from .models import GroupEvent, SchoolEvent, UserEvent


class SynchronizationManagerProtocol(Protocol):
    user_manager_class: type[Manager[User]]
    group_manager_class: type[Manager[Group]]
    school_manager_class: type[Manager[School]]
    role_manager_class: type[Manager[Role]]
    reader_session_builder: Callable[[Any, Any], Any]
    writer_session_builder: Callable[[Any, Any], Any]
    session_factory: Any

    async def handle_user_event(self, user_event: UserEvent):
        ...

    async def handle_group_event(self, group_event: GroupEvent):
        ...

    async def handle_school_event(self, school_event: SchoolEvent):
        ...
