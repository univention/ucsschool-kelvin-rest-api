# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from kelvin_connector.models import (
    GroupCreateEvent,
    GroupDeleteEvent,
    GroupModifyEvent,
    GroupPayload,
    SchoolCreateEvent,
    SchoolDeleteEvent,
    SchoolModifyEvent,
    SchoolPayload,
    UserCreateEvent,
    UserDeleteEvent,
    UserModifyEvent,
    UserPayload,
)
from loguru import logger
from provisioning_consumer_lib import AttributeMapping, UDMEventHandler
from provisioning_consumer_lib.consumer import Metadata, QueryEventObject
from pydantic import ValidationError
from typing_extensions import override

from .ports import SynchronizationManagerProtocol

if TYPE_CHECKING:  # pragma: no cover
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
            return False
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
        try:
            return await super().handle_event(event)
        except ValidationError as exc:
            logger.error("Dropping malformed event: {}", exc)
            return True

    @override
    async def _handle_create(self, metadata: Metadata, new: AttributeMapping) -> None:
        match new["objectType"]:
            case ObjectType.USERS:
                await self.synchronization_manager.handle_user_create(
                    UserCreateEvent(
                        timestamp=metadata["ts"],
                        sequence_number=metadata["sequence_number"],
                        new=UserPayload.validate(new),
                    )
                )
            case ObjectType.GROUPS:
                await self.synchronization_manager.handle_group_create(
                    GroupCreateEvent(
                        timestamp=metadata["ts"],
                        sequence_number=metadata["sequence_number"],
                        new=GroupPayload.validate(new),
                    )
                )
            case ObjectType.OUS:
                await self.synchronization_manager.handle_school_create(
                    SchoolCreateEvent(
                        timestamp=metadata["ts"],
                        sequence_number=metadata["sequence_number"],
                        new=SchoolPayload.validate(new),
                    )
                )
            case _:
                logger.error(f"Unknown object type {new['objectType']} in create event")

    @override
    async def _handle_modify(
        self,
        metadata: Metadata,
        old: AttributeMapping,
        new: AttributeMapping,
        has_moved: bool,
    ) -> None:
        # TODO has_moved is unused
        match new["objectType"]:
            case ObjectType.USERS:
                await self.synchronization_manager.handle_user_modify(
                    UserModifyEvent(
                        timestamp=metadata["ts"],
                        sequence_number=metadata["sequence_number"],
                        new=UserPayload.validate(new),
                    )
                )
            case ObjectType.GROUPS:
                await self.synchronization_manager.handle_group_modify(
                    GroupModifyEvent(
                        timestamp=metadata["ts"],
                        sequence_number=metadata["sequence_number"],
                        new=GroupPayload.validate(new),
                    )
                )
            case ObjectType.OUS:
                await self.synchronization_manager.handle_school_modify(
                    SchoolModifyEvent(
                        timestamp=metadata["ts"],
                        sequence_number=metadata["sequence_number"],
                        new=SchoolPayload.validate(new),
                    )
                )
            case _:
                logger.error(f"Unknown object type {new['objectType']} in modify event.")

    @override
    async def _handle_remove(self, metadata: Metadata, old: AttributeMapping) -> None:
        match old["objectType"]:
            case ObjectType.USERS:
                await self.synchronization_manager.handle_user_delete(
                    UserDeleteEvent(
                        timestamp=metadata["ts"],
                        sequence_number=metadata["sequence_number"],
                        old=UserPayload.validate(old),
                    )
                )
            case ObjectType.GROUPS:
                await self.synchronization_manager.handle_group_delete(
                    GroupDeleteEvent(
                        timestamp=metadata["ts"],
                        sequence_number=metadata["sequence_number"],
                        old=GroupPayload.validate(old),
                    )
                )
            case ObjectType.OUS:
                await self.synchronization_manager.handle_school_delete(
                    SchoolDeleteEvent(
                        timestamp=metadata["ts"],
                        sequence_number=metadata["sequence_number"],
                        old=SchoolPayload.validate(old),
                    )
                )
            case _:
                logger.error(f"Unknown object type {old['objectType']} in remove event.")
