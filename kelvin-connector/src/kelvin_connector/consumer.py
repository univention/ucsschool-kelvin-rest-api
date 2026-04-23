# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import enum
import os
import sys
from dataclasses import dataclass
from enum import auto
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from loguru import logger
from provisioning_consumer_lib import AttributeMapping, ConsumerModule, UDMEventHandler
from provisioning_consumer_lib.consumer import Metadata, QueryEventObject
from typing_extensions import override

if TYPE_CHECKING:
    from loguru import Logger


class SynchronizationHandler(Protocol):
    async def handle_user_event(self, user_event: UserEvent):
        ...

    async def handle_group_event(self, group_event: GroupEvent):
        ...

    async def handle_school_event(self, school_event: SchoolEvent):
        ...


class EventType(enum.Enum):
    CREATE = auto()
    MODIFY = auto()
    DELETE = auto()


@dataclass
class Event:
    timestamp: str
    sequence_number: int
    event_type: EventType
    old: None | dict[str, Any]
    new: None | dict[str, Any]


@dataclass
class UserEvent(Event):
    pass


@dataclass
class GroupEvent(Event):
    pass


@dataclass
class SchoolEvent(Event):
    pass


class UnknownTopicException(Exception):
    pass


class KelvinConnectorEventHandler(UDMEventHandler):
    def __init__(
        self, synchronization_handler: SynchronizationHandler, logger: Logger, *args, **kwargs
    ) -> None:
        self.synchronization_handler = synchronization_handler
        super().__init__(logger, *args, **kwargs)

    def _is_school_object_event(self, event: QueryEventObject) -> bool:
        if event["topic"] not in ["users/user", "groups/group", "container/ou"]:
            raise UnknownTopicException()
        return "ucsschoolRole" in event["body"]["old"] or "ucsschoolRole" in event["body"]["new"]

    @override
    def handle_event(self, event: QueryEventObject) -> bool:
        try:
            if not self._is_school_object_event(event):
                return False
        except UnknownTopicException:
            self.logger.error("Unknown topic encountered")
            return False
        return super().handle_event(event)

    @override
    def _handle_create(self, metadata: Metadata, new: AttributeMapping) -> None:
        """
        Called when a new object was created.

        :param str metadata: metadata of the create event
        :param dict new: new UDM objects attributes
        """
        match new["objectType"]:
            case "users/user":
                user_event = UserEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=None,
                    new=new,
                    event_type=EventType.CREATE,
                )
                self.synchronization_handler.handle_user_event(user_event)
            case "groups/group":
                group_event = GroupEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=None,
                    new=new,
                    event_type=EventType.CREATE,
                )
                self.synchronization_handler.handle_group_event(group_event)
            case "container/ou":
                school_event = SchoolEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=None,
                    new=new,
                    event_type=EventType.CREATE,
                )
                self.synchronization_handler.handle_school_event(school_event)

    @override
    def _handle_modify(
        self, metadata: Metadata, old: AttributeMapping, new: AttributeMapping, has_moved: bool
    ) -> None:
        """
        Called when an existing object was modified or moved.

        A move can be be detected by looking at <has_moved>. Attributes can be
        modified during a move.

        :param str metadata: metadata of the modify event
        :param dict old: previous UDM objects attributes
        :param dict new: new UDM objects attributes
        """
        match new["objectType"]:
            case "users/user":
                user_event = UserEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=new,
                    event_type=EventType.MODIFY,
                )
                self.synchronization_handler.handle_user_event(user_event)
            case "groups/group":
                group_event = GroupEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=new,
                    event_type=EventType.MODIFY,
                )
                self.synchronization_handler.handle_group_event(group_event)
            case "container/ou":
                school_event = SchoolEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=new,
                    event_type=EventType.MODIFY,
                )
                self.synchronization_handler.handle_school_event(school_event)
            case _:
                object_type = new["objectType"]
                logger.error(f"Unknown object type {object_type}")

    @override
    def _handle_remove(self, metadata: Metadata, old: AttributeMapping) -> None:
        """
        Called when an object was deleted.

        :param str metadata: metadata of the delete event
        :param dict old: previous UDM objects attributes
        """
        match old["objectType"]:
            case "users/user":
                user_event = UserEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=None,
                    event_type=EventType.DELETE,
                )
                self.synchronization_handler.handle_user_event(user_event)
            case "groups/group":
                group_event = GroupEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=None,
                    event_type=EventType.DELETE,
                )
                self.synchronization_handler.handle_group_event(group_event)
            case "container/ou":
                school_event = SchoolEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=None,
                    event_type=EventType.DELETE,
                )
                self.synchronization_handler.handle_school_event(school_event)
            case _:
                object_type = old["objectType"]
                logger.error(f"Unknown object type {object_type}")


def main():
    LDAP_SERVER_TYPE = os.environ.get("LDAP_SERVER_TYPE", None)
    if LDAP_SERVER_TYPE is None or LDAP_SERVER_TYPE != "master":
        logger.critical(f"Connector cannot run on {LDAP_SERVER_TYPE=}.")
        sys.exit(1)

    PROVISIONING_API_FQDN = os.environ.get("PROVISIONING_FQDN", None)
    if PROVISIONING_API_FQDN is None:
        logger.critical("Provisioning API FQDN is missing.")
        sys.exit(1)

    CONFIG_PATH = Path("/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/")

    event_handler = KelvinConnectorEventHandler(logger=logger)
    consumer = ConsumerModule(
        event_handler,
        name="kelvin-connector",
        provisioning_url=f"https://{PROVISIONING_API_FQDN}/univention/provisioning",
        config_path=CONFIG_PATH,
    )

    consumer.consume_loop()
