# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from kelvin_connector.models import (
    EventType,
    GroupEvent,
    SchoolEvent,
    UserEvent,
)
from loguru import logger
from provisioning_consumer_lib import AttributeMapping, UDMEventHandler
from provisioning_consumer_lib.consumer import Metadata, QueryEventObject
from typing_extensions import override

from .models import UDMEventObject
from .ports import SynchronizationManagerProtocol

if TYPE_CHECKING:
    from loguru import Logger


class ObjectType(enum.StrEnum):
    USERS = "users/user"
    GROUPS = "groups/group"
    OUS = "container/ou"


SUBSCRIBED_TOPICS = [ObjectType.OUS, ObjectType.GROUPS, ObjectType.USERS]


class UnknownTopicException(Exception):
    pass


class KelvinConnectorEventHandler(UDMEventHandler):
    def __init__(
        self,
        synchronization_manager: SynchronizationManagerProtocol,
        logger: Logger,
        *args,
        **kwargs,
    ) -> None:
        self.synchronization_manager = synchronization_manager
        super().__init__(logger, *args, **kwargs)

    @override
    async def is_relevant(self, event: QueryEventObject) -> bool:
        if event["topic"] not in SUBSCRIBED_TOPICS:
            raise UnknownTopicException()
        properties = None
        if "old" in event["body"] and "properties" in event["body"]["old"]:
            properties = event["body"]["old"]["properties"]
        elif "new" in event["body"] and "properties" in event["body"]["new"]:
            properties = event["body"]["new"]["properties"]
        if properties is None or "ucsschoolRole" not in properties:
            return False
        # TODO hard coded role checks
        if event["topic"] == "groups/group":
            return any(
                role.startswith("school_class") or role.startswith("workgroup")
                for role in properties["ucsschoolRole"]
            )
        return True

    @override
    async def handle_event(self, event: QueryEventObject) -> bool:
        self.logger.trace(event)
        UDMEventObject.validate(event)
        return await super().handle_event(event)

    @override
    async def _handle_create(self, metadata: Metadata, new: AttributeMapping) -> None:
        """
        Called when a new object was created.

        :param str metadata: metadata of the create event
        :param dict new: new UDM objects attributes
        """
        match new["objectType"]:
            case ObjectType.USERS:
                user_event = UserEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=None,
                    new=new,
                    event_type=EventType.CREATE,
                )
                await self.synchronization_manager.handle_user_event(user_event)
            case ObjectType.GROUPS:
                group_event = GroupEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=None,
                    new=new,
                    event_type=EventType.CREATE,
                )
                await self.synchronization_manager.handle_group_event(group_event)
            case ObjectType.OUS:
                school_event = SchoolEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=None,
                    new=new,
                    event_type=EventType.CREATE,
                )
                await self.synchronization_manager.handle_school_event(school_event)

    @override
    async def _handle_modify(
        self,
        metadata: Metadata,
        old: AttributeMapping,
        new: AttributeMapping,
        has_moved: bool,
    ) -> None:
        """
        Called when an existing object was modified or moved.

        A move can be be detected by looking at <has_moved>. Attributes can be
        modified during a move.

        :param str metadata: metadata of the modify event
        :param dict old: previous UDM objects attributes
        :param dict new: new UDM objects attributes
        """
        # TODO has_moved is unused
        match new["objectType"]:
            case ObjectType.USERS:
                user_event = UserEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=new,
                    event_type=EventType.MODIFY,
                )
                await self.synchronization_manager.handle_user_event(user_event)
            case ObjectType.GROUPS:
                group_event = GroupEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=new,
                    event_type=EventType.MODIFY,
                )
                await self.synchronization_manager.handle_group_event(group_event)
            case ObjectType.OUS:
                school_event = SchoolEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=new,
                    event_type=EventType.MODIFY,
                )
                await self.synchronization_manager.handle_school_event(school_event)
            case _:
                object_type = new["objectType"]
                logger.error(f"Unknown object type {object_type}")

    @override
    async def _handle_remove(self, metadata: Metadata, old: AttributeMapping) -> None:
        """
        Called when an object was deleted.

        :param str metadata: metadata of the delete event
        :param dict old: previous UDM objects attributes
        """
        match old["objectType"]:
            case ObjectType.USERS:
                user_event: UserEvent = UserEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=None,
                    event_type=EventType.DELETE,
                )
                await self.synchronization_manager.handle_user_event(user_event)
            case ObjectType.GROUPS:
                group_event = GroupEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=None,
                    event_type=EventType.DELETE,
                )
                await self.synchronization_manager.handle_group_event(group_event)
            case ObjectType.OUS:
                school_event = SchoolEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=None,
                    event_type=EventType.DELETE,
                )
                await self.synchronization_manager.handle_school_event(school_event)
            case _:
                object_type = old["objectType"]
                logger.error(f"Unknown object type {object_type}")
