# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import enum
import re
from typing import TYPE_CHECKING, cast

from kelvin_connector.models import (
    DeletePayload,
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

    logger: Logger


HOST_GROUP_NAME_RE = re.compile(r"OU(.*)-DC-(Edukativnetz|Verwaltungsnetz)")


class ObjectType(enum.StrEnum):
    USERS = "users/user"
    GROUPS = "groups/group"
    OUS = "container/ou"


SUBSCRIBED_TOPICS = [ObjectType.OUS, ObjectType.GROUPS, ObjectType.USERS]
DEFAULT_MAX_DELIVERIES = 3
DEFAULT_LONG_POLLING_TIMEOUT = 10


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
    def _filter(object_type: str, roles: list[str], seq_num: int, name: str = "") -> bool:
        match object_type:
            case (ObjectType.GROUPS):
                if any(
                    role.startswith("school_class") or role.startswith("workgroup") for role in roles
                ):
                    return True
                if HOST_GROUP_NAME_RE.match(name):
                    return True
                logger.info(
                    f"Skipping event {seq_num}: object filtered out (group or host_name), "
                    + f"object_type={object_type}, name={name}"
                )
                return False
            case (ObjectType.USERS):
                # Exam users are temporary copies (created under cn=examusers
                # for the duration of an exam, then deleted). They are
                # intentionally not cached.
                if any(role.startswith("exam_user:") for role in roles):
                    logger.info(
                        f"Skipping event {seq_num}: object filtered out (exam_user), "
                        + f"object_type={object_type}, name={name}"
                    )
                    return False
                return True
            case (ObjectType.OUS):
                return True
            case _:
                logger.info(
                    f"Skipping event {seq_num}: object filtered out (unknown object type), "
                    + f"object_type={object_type}), name={name}"
                )
                return False

    @override
    async def is_relevant(self, event: QueryEventObject) -> bool:
        self.logger.trace("Checking if event is relevant: {}", event)
        topic = event["topic"]
        seq_num = event["sequence_number"]
        body = event["body"]

        properties_old = None
        properties_new = None

        if "old" in body and "properties" in body["old"]:
            properties_old = body["old"]["properties"]

        if "new" in body and "properties" in body["new"]:
            properties_new = body["new"]["properties"]

        dn: str = str((body.get("new") or body.get("old") or {}).get("dn", ""))

        match (properties_old, properties_new):
            case ({"ucsschoolRole": roles} as properties, None):
                return self._filter(topic, roles, seq_num, cast(str, properties.get("name", "")))
            case (None, {"ucsschoolRole": roles} as properties):
                return self._filter(topic, roles, seq_num, cast(str, properties.get("name", "")))
            case ({"ucsschoolRole": _}, {"ucsschoolRole": roles_new} as properties):
                return self._filter(topic, roles_new, seq_num, cast(str, properties.get("name", "")))
            case _:
                self.logger.info(
                    f"Skipping event {seq_num}: old and new are None, topic={topic}, dn={dn}"
                )
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
        dn: str = str(new.get("dn", ""))
        public_id: str = str(new.get("properties", {}).get("univentionObjectIdentifier", ""))
        seq_num = metadata["sequence_number"]
        match new["objectType"]:
            case ObjectType.USERS:
                await self.synchronization_manager.handle_user_create(
                    UserCreateEvent(
                        timestamp=metadata["ts"],
                        sequence_number=seq_num,
                        new=UserPayload.validate(new),
                    )
                )
                self.logger.info(
                    f"Create user success: dn={dn}, public_id={public_id}, seq_num={seq_num}"
                )
            case ObjectType.GROUPS:
                if HOST_GROUP_NAME_RE.match(new["properties"].get("name", "")):
                    await self.synchronization_manager.handle_host_group_create(
                        HostGroupCreateEvent(
                            timestamp=metadata["ts"],
                            sequence_number=seq_num,
                            new=HostGroupPayload.validate(new),
                        )
                    )
                    self.logger.info(
                        f"Create host_group success: dn={dn}, public_id={public_id}, seq_num={seq_num}"
                    )
                else:
                    await self.synchronization_manager.handle_group_create(
                        GroupCreateEvent(
                            timestamp=metadata["ts"],
                            sequence_number=seq_num,
                            new=GroupPayload.validate(new),
                        )
                    )
                    self.logger.info(
                        f"Create group success: dn={dn}, public_id={public_id}, seq_num={seq_num}"
                    )
            case ObjectType.OUS:
                await self.synchronization_manager.handle_school_create(
                    SchoolCreateEvent(
                        timestamp=metadata["ts"],
                        sequence_number=seq_num,
                        new=SchoolPayload.validate(new),
                    )
                )
                self.logger.info(
                    f"Create school success: dn={dn}, public_id={public_id}, seq_num={seq_num}"
                )
            case _:
                self.logger.info(
                    f"Skipping create event {seq_num}: unknown object type {new['objectType']}, dn={dn}"
                )

    @override
    async def _handle_modify(
        self,
        metadata: Metadata,
        old: AttributeMapping,
        new: AttributeMapping,
        has_moved: bool,
    ) -> None:
        # has_moved needs no special handling: the modify handlers refresh
        # the DN mapping from the event's new dn unconditionally.
        dn: str = str(new.get("dn", ""))
        public_id: str = str(new.get("properties", {}).get("univentionObjectIdentifier", ""))
        seq_num = metadata["sequence_number"]
        match new["objectType"]:
            case ObjectType.USERS:
                await self.synchronization_manager.handle_user_modify(
                    UserModifyEvent(
                        timestamp=metadata["ts"],
                        sequence_number=seq_num,
                        new=UserPayload.validate(new),
                    )
                )
                self.logger.info(
                    f"Modify user success: dn={dn}, public_id={public_id}, seq_num={seq_num}"
                )
            case ObjectType.GROUPS:
                if HOST_GROUP_NAME_RE.match(new["properties"].get("name", "")):
                    await self.synchronization_manager.handle_host_group_modify(
                        HostGroupModifyEvent(
                            timestamp=metadata["ts"],
                            sequence_number=seq_num,
                            new=HostGroupPayload.validate(new),
                        )
                    )
                    self.logger.info(
                        f"Modify host_group success: dn={dn}, public_id={public_id}, seq_num={seq_num}"
                    )
                else:
                    await self.synchronization_manager.handle_group_modify(
                        GroupModifyEvent(
                            timestamp=metadata["ts"],
                            sequence_number=seq_num,
                            new=GroupPayload.validate(new),
                        )
                    )
                    self.logger.info(
                        f"Modify group success: dn={dn}, public_id={public_id}, seq_num={seq_num}"
                    )
            case ObjectType.OUS:
                await self.synchronization_manager.handle_school_modify(
                    SchoolModifyEvent(
                        timestamp=metadata["ts"],
                        sequence_number=seq_num,
                        new=SchoolPayload.validate(new),
                    )
                )
                self.logger.info(
                    f"Modify school success: dn={dn}, public_id={public_id}, seq_num={seq_num}"
                )
            case _:
                self.logger.info(
                    f"Skipping modify event {seq_num}: unknown object type {new['objectType']}, dn={dn}"
                )

    @override
    async def _handle_remove(self, metadata: Metadata, old: AttributeMapping) -> None:
        # Deletion only needs the identifier: the rest of a deleted object's
        # state may be malformed and must not prevent removing it from the
        # cache — see DeletePayload.
        dn: str = str(old.get("dn", ""))
        public_id: str = str(old.get("properties", {}).get("univentionObjectIdentifier", ""))
        seq_num = metadata["sequence_number"]
        match old["objectType"]:
            case ObjectType.USERS:
                await self.synchronization_manager.handle_user_delete(
                    UserDeleteEvent(
                        timestamp=metadata["ts"],
                        sequence_number=seq_num,
                        old=DeletePayload.validate(old),
                    )
                )
                self.logger.info(
                    f"Delete user success: dn={dn}, public_id={public_id}, seq_num={seq_num}"
                )
            case ObjectType.GROUPS:
                if HOST_GROUP_NAME_RE.match(old["properties"].get("name", "")):
                    await self.synchronization_manager.handle_host_group_delete(
                        HostGroupDeleteEvent(
                            timestamp=metadata["ts"],
                            sequence_number=seq_num,
                            old=HostGroupPayload.validate(old),
                        )
                    )
                    self.logger.info(
                        f"Delete host_group success: dn={dn}, public_id={public_id}, seq_num={seq_num}"
                    )
                else:
                    await self.synchronization_manager.handle_group_delete(
                        GroupDeleteEvent(
                            timestamp=metadata["ts"],
                            sequence_number=seq_num,
                            old=DeletePayload.validate(old),
                        )
                    )
                    self.logger.info(
                        f"Delete group success: dn={dn}, public_id={public_id}, seq_num={seq_num}"
                    )
            case ObjectType.OUS:
                await self.synchronization_manager.handle_school_delete(
                    SchoolDeleteEvent(
                        timestamp=metadata["ts"],
                        sequence_number=seq_num,
                        old=DeletePayload.validate(old),
                    )
                )
                self.logger.info(
                    f"Delete school success: dn={dn}, public_id={public_id}, seq_num={seq_num}"
                )
            case _:
                self.logger.info(
                    f"Skipping delete event {seq_num}: unknown object type {old['objectType']}, dn={dn}"
                )


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
    - Malformed events (ValidationError) are dropped immediately and without
      crashing: retrying cannot fix them, and the handler never touched any
      state, so there is nothing a restart would clean up.

    Every event is handled in its own database transaction that rolls back
    on failure, so a crashed event never leaves partial state behind.

    TODO: upstream this policy into provisioning_consumer_lib.
    """

    def __init__(
        self, handler: EventHandler, *args, max_deliveries: int = DEFAULT_MAX_DELIVERIES, **kwargs
    ) -> None:
        super().__init__(handler, *args, **kwargs)
        self.max_deliveries = max_deliveries

    @override
    async def process_one_event(self, long_polling_timeout: int = DEFAULT_LONG_POLLING_TIMEOUT) -> None:
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
        except ValidationError as exc:
            self.logger.critical(
                f"Dropping malformed event {seq_num}: {exc.model.__name__} failed validation: "
                + f"{exc.errors()}\nEvent: {event!r}"
            )
            await self._acknowledge_event(event)
            return
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
