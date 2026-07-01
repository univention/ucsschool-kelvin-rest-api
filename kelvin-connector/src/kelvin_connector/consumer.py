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
                    "Skipping event {}: Object is not a school class, work group or host group. "
                    + "object_type={}, name={}",
                    seq_num,
                    object_type,
                    name,
                )
                return False
            case (ObjectType.USERS):
                # Exam users are temporary copies (created under cn=examusers
                # for the duration of an exam, then deleted). They are
                # intentionally not cached.
                is_exam_user = any(role.startswith("exam_user:") for role in roles)
                if is_exam_user:
                    logger.info(
                        "Skipping event {}: Object is an exam user. object_type={}, name={}",
                        seq_num,
                        object_type,
                        name,
                    )
                    return False
                return True
            case (ObjectType.OUS):
                return True
            case _:
                logger.info(
                    "Skipping event {}: Object type is not recognized. object_type={}, name={}",
                    seq_num,
                    object_type,
                    name,
                )
                return False

    @override
    async def is_relevant(self, event: QueryEventObject) -> bool:
        self.logger.trace("Checking if event is relevant: {}", event)
        topic = event["topic"]
        seq_num = event["sequence_number"]
        body: dict[str, AttributeMapping] = event["body"]

        properties_old: dict[str, list[str]] | None = None
        properties_new: dict[str, list[str]] | None = None

        if "old" in body and "properties" in body["old"]:
            properties_old = body["old"]["properties"]

        if "new" in body and "properties" in body["new"]:
            properties_new = body["new"]["properties"]

        body_new: AttributeMapping | None = body.get("new")
        body_old: AttributeMapping | None = body.get("old")
        dn: str = cast(str, (body_new or body_old or {}).get("dn", ""))

        match (properties_old, properties_new):
            case ({"ucsschoolRole": roles} as properties, None):
                return self._filter(topic, roles, seq_num, str(properties.get("name", "")))
            case (None, {"ucsschoolRole": roles} as properties):
                return self._filter(topic, roles, seq_num, str(properties.get("name", "")))
            case ({"ucsschoolRole": _}, {"ucsschoolRole": roles_new} as properties):
                return self._filter(topic, roles_new, seq_num, str(properties.get("name", "")))
            case _:
                self.logger.info(
                    "Skipping event {}: no ucsschoolRole in old or new UDM properties, "
                    + "topic={}, dn={}",
                    seq_num,
                    topic,
                    dn,
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
        dn: str = cast(str, new.get("dn", ""))
        new_properties = cast(AttributeMapping, new.get("properties", {}))
        public_id: str = cast(str, new_properties.get("univentionObjectIdentifier", ""))
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
                    "Create user event processed: dn={}, public_id={}, seq_num={}",
                    dn,
                    public_id,
                    seq_num,
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
                        "Create host_group event processed: dn={}, public_id={}, seq_num={}",
                        dn,
                        public_id,
                        seq_num,
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
                        "Create group event processed: dn={}, public_id={}, seq_num={}",
                        dn,
                        public_id,
                        seq_num,
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
                    "Create school event processed: dn={}, public_id={}, seq_num={}",
                    dn,
                    public_id,
                    seq_num,
                )
            case _:
                self.logger.info(
                    "Skipping create event {}: unknown object type {}, dn={}\nNew: {}",
                    seq_num,
                    cast(str, new["objectType"]),
                    dn,
                    new,
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
        dn: str = cast(str, new.get("dn", ""))
        new_properties = cast(AttributeMapping, new.get("properties", {}))
        public_id: str = cast(str, new_properties.get("univentionObjectIdentifier", ""))
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
                    "Modify user event processed: dn={}, public_id={}, seq_num={}",
                    dn,
                    public_id,
                    seq_num,
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
                        "Modify host_group event processed: dn={}, public_id={}, seq_num={}",
                        dn,
                        public_id,
                        seq_num,
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
                        "Modify group event processed: dn={}, public_id={}, seq_num={}",
                        dn,
                        public_id,
                        seq_num,
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
                    "Modify school event processed: dn={}, public_id={}, seq_num={}",
                    dn,
                    public_id,
                    seq_num,
                )
            case _:
                self.logger.info(
                    "Skipping modify event {}: unknown object type {}, dn={}\nOld: {}\nNew: {}",
                    seq_num,
                    cast(str, new["objectType"]),
                    dn,
                    old,
                    new,
                )

    @override
    async def _handle_remove(self, metadata: Metadata, old: AttributeMapping) -> None:
        # Deletion only needs the identifier: the rest of a deleted object's
        # state may be malformed and must not prevent removing it from the
        # cache — see DeletePayload.
        dn: str = cast(str, old.get("dn", ""))
        old_properties = cast(AttributeMapping, old.get("properties", {}))
        public_id: str = cast(str, old_properties.get("univentionObjectIdentifier", ""))
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
                    "Delete user event processed: dn={}, public_id={}, seq_num={}",
                    dn,
                    public_id,
                    seq_num,
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
                        "Delete host_group event processed: dn={}, public_id={}, seq_num={}",
                        dn,
                        public_id,
                        seq_num,
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
                        "Delete group event processed: dn={}, public_id={}, seq_num={}",
                        dn,
                        public_id,
                        seq_num,
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
                    "Delete school event processed: dn={}, public_id={}, seq_num={}",
                    dn,
                    public_id,
                    seq_num,
                )
            case _:
                self.logger.info(
                    "Skipping delete event {}: unknown object type {}, dn={}\nOld: {}",
                    seq_num,
                    cast(str, old["objectType"]),
                    dn,
                    old,
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
        self.max_deliveries: int = max_deliveries

    @override
    async def process_one_event(self, long_polling_timeout: int = DEFAULT_LONG_POLLING_TIMEOUT) -> None:
        event = await self._fetch_event(long_polling_timeout)
        if not event:
            # If the queue is empty, long polling timed out without new events.
            self.logger.debug("Long polling timeout, no more events.")
            return

        seq_num = event["sequence_number"]
        self.logger.debug("Event {} has been fetched.", seq_num)
        if not await self.handler.is_relevant(event):
            self.logger.debug("Skipped and acknowledged event {} as requested.", seq_num)
            await self._acknowledge_event(event)
            return

        try:
            handled = await self.handler.handle_event(event)
        except ValidationError as exc:
            self.logger.error(
                "Dropping malformed event {}: {} failed validation: {}\nEvent: {!r}",
                seq_num,
                exc.model.__name__,
                exc.errors(),
                event,
            )
            await self._acknowledge_event(event)
            return
        except Exception:
            num_delivered = event["num_delivered"]
            if num_delivered < self.max_deliveries:
                self.logger.error(
                    "Event {} failed on delivery {}/{}; "
                    + "crashing without acknowledgement, the event will be redelivered.",
                    seq_num,
                    num_delivered,
                    self.max_deliveries,
                )
                raise
            self.logger.critical(
                "Dropping event {} after {} failed deliveries: {!r}",
                seq_num,
                num_delivered,
                event,
            )
            await self._acknowledge_event(event)
            raise

        if handled:
            self.logger.debug("Event {} has been processed successfully.", seq_num)
            await self._acknowledge_event(event)
        else:
            self.logger.debug("Event {} has not been processed.", seq_num)
