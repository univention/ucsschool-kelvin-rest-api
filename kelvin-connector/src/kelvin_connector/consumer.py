# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import enum
import re
from typing import TYPE_CHECKING

from kelvin_connector.models import (
    GroupCreateEvent,
    GroupDeleteEvent,
    GroupModifyEvent,
    GroupPayload,
    HostGroupCreateEvent,
    HostGroupDeleteEvent,
    HostGroupModifyEvent,
    HostGroupPayload,
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
from provisioning_consumer_lib import (
    AttributeMapping,
    ConsumerModule,
    EventHandler,
    UDMEventHandler,
)
from provisioning_consumer_lib.consumer import Metadata, QueryEventObject
from pydantic import ValidationError
from typing_extensions import override

from .ports import SynchronizationManagerProtocol

if TYPE_CHECKING:  # pragma: no cover
    from types import TracebackType

    from loguru import Logger


HOST_GROUP_NAME_RE = re.compile(r"OU(.*)-DC-(Edukativnetz|Verwaltungsnetz)")


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

    @staticmethod
    def _filter(object_type: str, roles: list[str], name: str = "") -> bool:
        match object_type:
            case (ObjectType.GROUPS):
                if any(
                    role.startswith("school_class") or role.startswith("workgroup") for role in roles
                ):
                    return True
                if HOST_GROUP_NAME_RE.match(name):
                    return True
                return False
            case (ObjectType.USERS | ObjectType.OUS):
                return True
            case _:
                return False

    @override
    async def is_relevant(self, event: QueryEventObject) -> bool:
        self.logger.trace("Checking if event is relevant: {}", event)
        topic = event["topic"]
        body = event["body"]

        properties_old = None
        properties_new = None

        if "old" in body and "properties" in body["old"]:
            properties_old = body["old"]["properties"]

        if "new" in body and "properties" in body["new"]:
            properties_new = body["new"]["properties"]

        match (properties_old, properties_new):
            case ({"ucsschoolRole": roles} as properties, None):
                return self._filter(topic, roles, properties.get("name", ""))
            case (None, {"ucsschoolRole": roles} as properties):
                return self._filter(topic, roles, properties.get("name", ""))
            case ({"ucsschoolRole": _}, {"ucsschoolRole": roles_new} as properties):
                return self._filter(topic, roles_new, properties.get("name", ""))
            case _:
                return False

    @override
    async def handle_event(self, event: QueryEventObject) -> bool:
        self.logger.trace(event)
        return await super().handle_event(event)

    @override
    async def _handle_error(
        self,
        metadata: Metadata,
        old: AttributeMapping,
        new: AttributeMapping,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        # The library default logs the full traceback here before re-raising,
        # duplicating the crash output. What happens to a failed event is
        # decided and logged by KelvinConsumerModule — just propagate.
        assert exc_value is not None
        raise exc_value.with_traceback(exc_traceback)

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
                if HOST_GROUP_NAME_RE.match(new["properties"].get("name", "")):
                    await self.synchronization_manager.handle_host_group_create(
                        HostGroupCreateEvent(
                            timestamp=metadata["ts"],
                            sequence_number=metadata["sequence_number"],
                            new=HostGroupPayload.validate(new),
                        )
                    )
                else:
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
                if HOST_GROUP_NAME_RE.match(new["properties"].get("name", "")):
                    await self.synchronization_manager.handle_host_group_modify(
                        HostGroupModifyEvent(
                            timestamp=metadata["ts"],
                            sequence_number=metadata["sequence_number"],
                            new=HostGroupPayload.validate(new),
                        )
                    )
                else:
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
                if HOST_GROUP_NAME_RE.match(old["properties"].get("name", "")):
                    await self.synchronization_manager.handle_host_group_delete(
                        HostGroupDeleteEvent(
                            timestamp=metadata["ts"],
                            sequence_number=metadata["sequence_number"],
                            old=HostGroupPayload.validate(old),
                        )
                    )
                else:
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


class KelvinConsumerModule(ConsumerModule):
    """ConsumerModule with a bounded retry policy for failing events.

    The library default crashes without acknowledging a failed event, so a
    deterministically failing event is redelivered after every restart and
    halts the whole sync (poison pill). Instead:

    - While the event has deliveries left, crash *without* acknowledging:
      transient failures (database hiccups, event-ordering races) are
      retried via redelivery after the restart.
    - Once the delivery budget is exhausted, log the full event, acknowledge
      it and crash anyway: the dropped event is documented, the process
      restarts with a clean state and continues with the next event. Since
      modify events create missing objects, the next event touching the
      same object repairs the dropped state.
    - Malformed events (ValidationError) are dropped immediately — retrying
      cannot fix them.

    Every event is handled in its own database transaction that rolls back
    on failure, so a crashed event never leaves partial state behind.

    TODO: upstream this policy into provisioning_consumer_lib.
    """

    def __init__(self, handler: EventHandler, *args, max_deliveries: int = 3, **kwargs) -> None:
        super().__init__(handler, *args, **kwargs)
        self.max_deliveries = max_deliveries

    @override
    async def process_one_event(self, long_polling_timeout: int = 10) -> None:
        event = await self._fetch_event(long_polling_timeout)
        if not event:
            # If the queue is empty, long polling timed out without new events.
            self.logger.debug("Long polling timeout, no more events.")
            return

        seq_num = event["sequence_number"]
        self.logger.debug(f"Event {seq_num} has been fetched.")
        if not await self.handler.is_relevant(event):
            self.logger.debug(f"Skipped and acknowledged event {seq_num} as requested.")
            await self._acknowledge_event(event)
            return

        try:
            handled = await self.handler.handle_event(event)
        except ValidationError:
            self.logger.critical(f"Dropping malformed event {seq_num}: {event!r}")
            await self._acknowledge_event(event)
            raise
        except Exception:
            num_delivered = event["num_delivered"]
            if num_delivered < self.max_deliveries:
                self.logger.error(
                    f"Event {seq_num} failed on delivery {num_delivered}/{self.max_deliveries}; "
                    "crashing without acknowledgement, the event will be redelivered."
                )
                raise
            self.logger.critical(
                f"Dropping event {seq_num} after {num_delivered} failed deliveries: {event!r}"
            )
            await self._acknowledge_event(event)
            raise

        if handled:
            self.logger.debug(f"Event {seq_num} has been processed successfully.")
            await self._acknowledge_event(event)
        else:
            self.logger.debug(f"Event {seq_num} has not been processed.")
