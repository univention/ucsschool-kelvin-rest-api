# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any

from kelvin_connector.models import (
    EventType,
    GroupEvent,
    SchoolEvent,
    UserEvent,
)
from provisioning_consumer_lib import AttributeMapping, UDMEventHandler
from provisioning_consumer_lib.consumer import Metadata, QueryEventObject
from typing_extensions import override

from .ports import SynchronizationManagerProtocol

if TYPE_CHECKING:
    from loguru import Logger


class UnknownTopicException(Exception):
    pass


class KelvinConnectorEventHandler(UDMEventHandler):
    def __init__(
        self, synchronization_manager: SynchronizationManagerProtocol, logger: Logger, *args, **kwargs
    ) -> None:
        self.synchronization_manager = synchronization_manager
        super().__init__(logger, *args, **kwargs)

    def _run_sync(self, coroutine: Coroutine[Any, Any, None]) -> None:
        asyncio.run(coroutine)

    def _is_school_object_event(self, event: QueryEventObject) -> bool:
        if event["topic"] not in ["users/user", "groups/group", "container/ou"]:
            raise UnknownTopicException()
        if "old" in event["body"] and "properties" in event["body"]["old"]:
            return "ucsschoolRole" in event["body"]["old"]["properties"]
        elif "new" in event["body"] and "properties" in event["body"]["new"]:
            return "ucsschoolRole" in event["body"]["new"]["properties"]
        return False

    @override
    def handle_event(self, event: QueryEventObject) -> bool:
        try:
            if not self._is_school_object_event(event):
                self.logger.debug(f"Event {event} is no school object event.")
                return True
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
                self._run_sync(self.synchronization_manager.handle_user_event(user_event))
            case "groups/group":
                group_event = GroupEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=None,
                    new=new,
                    event_type=EventType.CREATE,
                )
                self._run_sync(self.synchronization_manager.handle_group_event(group_event))
            case "container/ou":
                school_event = SchoolEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=None,
                    new=new,
                    event_type=EventType.CREATE,
                )
                self._run_sync(self.synchronization_manager.handle_school_event(school_event))

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
                self._run_sync(self.synchronization_manager.handle_user_event(user_event))
            case "groups/group":
                group_event = GroupEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=new,
                    event_type=EventType.MODIFY,
                )
                self._run_sync(self.synchronization_manager.handle_group_event(group_event))
            case "container/ou":
                school_event = SchoolEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=new,
                    event_type=EventType.MODIFY,
                )
                self._run_sync(self.synchronization_manager.handle_school_event(school_event))
            case _:
                self.logger.error(f"Unknown object type {new['objectType']}")

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
                self._run_sync(self.synchronization_manager.handle_user_event(user_event))
            case "groups/group":
                group_event = GroupEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=None,
                    event_type=EventType.DELETE,
                )
                self._run_sync(self.synchronization_manager.handle_group_event(group_event))
            case "container/ou":
                school_event = SchoolEvent(
                    timestamp=metadata["ts"],
                    sequence_number=metadata["sequence_number"],
                    old=old,
                    new=None,
                    event_type=EventType.DELETE,
                )
                self._run_sync(self.synchronization_manager.handle_school_event(school_event))
            case _:
                self.logger.error(f"Unknown object type {old['objectType']}")
