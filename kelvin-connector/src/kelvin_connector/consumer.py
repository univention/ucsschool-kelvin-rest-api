# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kelvin_connector.models import (
    EventType,
    GroupEvent,
    SchoolEvent,
    UserEvent,
)
from kelvin_connector.sync import SynchronizationManager
from loguru import logger
from provisioning_consumer_lib import AttributeMapping, ConsumerModule, UDMEventHandler
from provisioning_consumer_lib.consumer import Metadata, QueryEventObject
from typing_extensions import override
from ucsschool_objects.core.adapters.sqlalchemy.session import (
    build_engine,
    build_kelvin_storage_session_factory,
    build_settings,
)

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
        properties = None
        if "old" in event["body"] and "properties" in event["body"]["old"]:
            properties = event["body"]["old"]["properties"]
        elif "new" in event["body"] and "properties" in event["body"]["new"]:
            properties = event["body"]["new"]["properties"]
        if properties is None or "ucsschoolRole" not in properties:
            return False
        if event["topic"] == "groups/group":
            return any(
                role.startswith("school_class") or role.startswith("workgroup")
                for role in properties["ucsschoolRole"]
            )
        return True

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

    try:
        settings = build_settings()
    except RuntimeError as e:
        logger.critical(str(e))
        sys.exit(1)

    engine = build_engine(settings)
    storage_factory = build_kelvin_storage_session_factory(engine)
    synchronization_manager = SynchronizationManager(storage_factory=storage_factory)

    CONFIG_DIR = Path("/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/")

    event_handler = KelvinConnectorEventHandler(synchronization_manager, logger=logger)
    consumer = ConsumerModule(
        event_handler,
        name="kelvin-connector",
        provisioning_url=f"https://{PROVISIONING_API_FQDN}/univention/provisioning",
        config_dir=CONFIG_DIR,
    )

    consumer.consume_loop()
