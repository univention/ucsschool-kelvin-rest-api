import enum
from dataclasses import dataclass
from enum import auto
from typing import Any, Callable, final

from ucsschool_objects.core.domain.models import Group, Role, School, User
from ucsschool_objects.core.domain.ports import Manager


class EventType(enum.Enum):
    CREATE = auto()
    MODIFY = auto()
    DELETE = auto()


UDM_USER_PROPERTY_MAPPING = {
    "ucsschoolRecordUID": "record_uid",
    "ucsschoolSourceUID": "source_uid",
    "username": "name",
    "firstname": "firstname",
    "lastname": "lastname",
    "disabled": "active",
    "school": "school_memberships",
    "ucsschoolLegalWard": "legal_wards",
    "ucsschoolLegalGuardian": "legal_guardians",
    "e-mail": "email",
    "birthday": "birthday",
    "userexpiry": "expiration_date",
}

UDM_GROUP_PROPERTY_MAPPING = {
    "ucsschoolRecordUID": "record_uid",
    "ucsschoolSourceUID": "source_uid",
    "name": "name",
    "allowedEmailUsers": "allowed_email_senders_users",
    "allowedEmailGroups": "allowed_email_senders_groups",
    "school": "school",
}

UDM_SCHOOL_PROPERTY_MAPPING = {
    "name": "name",
    "displayName": "display_name",
    "ucsschoolHomeShareFileServer": "home_share_file_server",
    "ucsschoolClassShareFileServer": "class_share_file_server",
    # TODO
    # educational_servers
    # administrative_servers
}


class UDMPropertyMapper:
    def __init__(self):
        self._mappings: dict[str, str] = {}
        self._hooks: dict[str, Callable[..., Any]] = {}

    def register_map(self, mapping: dict[str, str]) -> None:
        for source_key, target_key in mapping.items():
            if source_key in self._mappings:
                raise ValueError(f"Source key '{source_key}' is already registered.")
            if target_key in self._mappings.values():
                raise ValueError(f"Target key '{target_key}' is already registered.")
            self._mappings[source_key] = target_key

    def register(self, source_key: str, target_key: str) -> None:
        """Register a 1:1 mapping between source and target keys."""
        if source_key in self._mappings:
            raise ValueError(f"Source key '{source_key}' is already registered.")
        if target_key in self._mappings.values():
            raise ValueError(f"Target key '{target_key}' is already registered.")
        self._mappings[source_key] = target_key

    def register_hook(self, source_key: str, func: Callable[..., Any]):
        """Register a hook function for a source key to transform its value."""
        if source_key not in self._mappings:
            raise ValueError(f"Source key '{source_key}' is not registered.")

        self._hooks[source_key] = func

    def map(self, source: dict[str, Any]) -> dict[str, Any]:
        """Map source dictionary to a new dictionary using registered mappings."""
        result = {}

        for source_key, target_key in self._mappings.items():
            if source_key not in source:
                continue

            target_key = self._mappings[source_key]
            value = source[source_key]

            if source_key in self._hooks:
                value = self._hooks[source_key](value)

            result[target_key] = value

        return result


@dataclass
class Event:
    timestamp: str
    sequence_number: int
    event_type: EventType


@dataclass
class UserEvent(Event):
    old: None | dict[str, Any]
    new: None | dict[str, Any]


@dataclass
class GroupEvent(Event):
    pass


@dataclass
class SchoolEvent(Event):
    pass


@final
class Synchronization:
    def __init__(
        self,
        user_manager: Manager[User],
        group_manager: Manager[Group],
        school_manager: Manager[School],
        role_manager: Manager[Role],
    ) -> None:
        self.user_manager = user_manager
        self.group_manager = group_manager
        self.school_manager = school_manager
        self.role_manager = role_manager
        self._build_property_mapper()

    def _build_property_mapper(self):
        self.udm_property_mapper = UDMPropertyMapper()
        self.udm_property_mapper.register_map(UDM_USER_PROPERTY_MAPPING)
        self.udm_property_mapper.register_hook("disabled", lambda x: not x)

    async def handle_user_event(self, user_event: UserEvent):
        match user_event.event_type:
            case EventType.CREATE:
                if user_event.new is None:
                    return
                user_event.new["school"]
                self.school_manager.get()
                user_keyword_arguments = self.udm_property_mapper.map(user_event.new["properties"])
                user = User(public_id=user_event.new["id"], **user_keyword_arguments)
                await self.user_manager.create(user)
            case EventType.DELETE:
                if user_event.new is None:
                    return
                await self.user_manager.delete(user_event.new["id"])
            case EventType.MODIFY:
                pass

    async def handle_group_event(self, group_event: GroupEvent):
        match group_event.event_type:
            case EventType.CREATE:
                pass
            case EventType.DELETE:
                pass
            case EventType.MODIFY:
                pass

    async def handle_school_event(self, school_event: SchoolEvent):
        match school_event.event_type:
            case EventType.CREATE:
                pass
            case EventType.DELETE:
                pass
            case EventType.MODIFY:
                pass
