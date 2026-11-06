# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
"""Process CCF tasks: decide relevance, dispatch to the synchronization manager."""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from loguru import logger
from pydantic import ValidationError

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

from .ports import CoroutineRunnerProtocol, SynchronizationManagerProtocol

HOST_GROUP_NAME_RE = re.compile(r"OU(.*)-DC-(Edukativnetz|Verwaltungsnetz)")

# A CCF task as handed to the Python callback (see the CCF README).
Task = Mapping[str, Any]


class ObjectType(enum.StrEnum):
    USERS = "users/user"
    GROUPS = "groups/group"
    OUS = "container/ou"


class OutcomeKind(enum.Enum):
    CREATED = enum.auto()
    MODIFIED = enum.auto()
    DELETED = enum.auto()
    SKIPPED = enum.auto()
    FAILURE = enum.auto()
    PERMANENT_FAILURE = enum.auto()


@dataclass(frozen=True)
class Outcome:
    kind: OutcomeKind
    msg: str | None = None


def _filter(object_type: str, roles: list[str], seq_num: int, name: str = "") -> bool:
    match object_type:
        case ObjectType.GROUPS:
            if any(role.startswith("school_class") or role.startswith("workgroup") for role in roles):
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
        case ObjectType.USERS:
            # Exam users are temporary copies (created under cn=examusers
            # for the duration of an exam, then deleted). They are
            # intentionally not cached.
            if any(role.startswith("exam_user:") for role in roles):
                logger.info(
                    "Skipping event {}: Object is an exam user. object_type={}, name={}",
                    seq_num,
                    object_type,
                    name,
                )
                return False
            return True
        case ObjectType.OUS:
            return True
        case _:
            logger.info(
                "Skipping event {}: Object type is not recognized. object_type={}, name={}",
                seq_num,
                object_type,
                name,
            )
            return False


def is_relevant(task: Task) -> bool:
    object_type: str = task["udm_module"]
    seq_num: int = task["seq_number"]
    old: Mapping[str, Any] = task["old"]
    new: Mapping[str, Any] = task["new"]
    properties_old = old.get("properties")
    properties_new = new.get("properties")

    match (properties_old, properties_new):
        case ({"ucsschoolRole": roles} as properties, None):
            return _filter(object_type, roles, seq_num, str(properties.get("name", "")))
        case (None, {"ucsschoolRole": roles} as properties):
            return _filter(object_type, roles, seq_num, str(properties.get("name", "")))
        case ({"ucsschoolRole": _}, {"ucsschoolRole": roles_new} as properties):
            return _filter(object_type, roles_new, seq_num, str(properties.get("name", "")))
        case _:
            logger.info(
                "Skipping event {}: no ucsschoolRole in old or new UDM properties, "
                + "object_type={}, dn={}",
                seq_num,
                object_type,
                (new or old).get("dn", ""),
            )
            return False


def _validation_summary(exc: ValidationError) -> str:
    """Failing fields and messages, without the values (they hold personal data)."""
    fields = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors(include_url=False, include_context=False, include_input=False)
    )
    return f"{exc.title} failed validation: {fields}"


class TaskProcessor:
    """Turns a relevant CCF task into a call of the synchronization manager."""

    def __init__(self, synchronization_manager: SynchronizationManagerProtocol) -> None:
        self.synchronization_manager: SynchronizationManagerProtocol = synchronization_manager

    async def process(self, task: Task) -> Outcome:
        with logger.contextualize(request_id=task["request_id"]):
            try:
                if task["old"] and task["new"]:
                    return await self._modify(task)
                if task["new"]:
                    return await self._create(task)
                return await self._remove(task)
            except ValidationError as exc:
                summary = _validation_summary(exc)
                logger.error("Event {} is malformed: {}", task["seq_number"], summary)
                return Outcome(OutcomeKind.PERMANENT_FAILURE, summary)

    @staticmethod
    def _log_processed(operation: str, kind: str, payload: Mapping[str, Any], seq_num: int) -> None:
        logger.info(
            "{} {} event processed: dn={}, public_id={}, seq_num={}",
            operation,
            kind,
            payload.get("dn", ""),
            payload.get("properties", {}).get("univentionObjectIdentifier", ""),
            seq_num,
        )

    @staticmethod
    def _skip_unknown_type(operation: str, task: Task) -> Outcome:
        logger.info(
            "Skipping {} event {}: unknown object type {}, dn={}",
            operation,
            task["seq_number"],
            task["udm_module"],
            task["dn"],
        )
        return Outcome(OutcomeKind.SKIPPED)

    async def _create(self, task: Task) -> Outcome:
        new = task["new"]
        meta = {"timestamp": task["ts"], "sequence_number": task["seq_number"]}
        sync = self.synchronization_manager
        match task["udm_module"]:
            case ObjectType.USERS:
                await sync.handle_user_create(
                    UserCreateEvent(**meta, new=UserPayload.model_validate(new))
                )
                kind = "user"
            case ObjectType.GROUPS if HOST_GROUP_NAME_RE.match(new["properties"].get("name", "")):
                await sync.handle_host_group_create(
                    HostGroupCreateEvent(**meta, new=HostGroupPayload.model_validate(new))
                )
                kind = "host_group"
            case ObjectType.GROUPS:
                await sync.handle_group_create(
                    GroupCreateEvent(**meta, new=GroupPayload.model_validate(new))
                )
                kind = "group"
            case ObjectType.OUS:
                await sync.handle_school_create(
                    SchoolCreateEvent(**meta, new=SchoolPayload.model_validate(new))
                )
                kind = "school"
            case _:
                return self._skip_unknown_type("create", task)
        self._log_processed("Create", kind, new, task["seq_number"])
        return Outcome(OutcomeKind.CREATED)

    async def _modify(self, task: Task) -> Outcome:
        # A move or rename needs no special handling: the modify handlers
        # refresh the DN mapping from the event's new dn unconditionally.
        new = task["new"]
        meta = {"timestamp": task["ts"], "sequence_number": task["seq_number"]}
        sync = self.synchronization_manager
        match task["udm_module"]:
            case ObjectType.USERS:
                await sync.handle_user_modify(
                    UserModifyEvent(**meta, new=UserPayload.model_validate(new))
                )
                kind = "user"
            case ObjectType.GROUPS if HOST_GROUP_NAME_RE.match(new["properties"].get("name", "")):
                await sync.handle_host_group_modify(
                    HostGroupModifyEvent(**meta, new=HostGroupPayload.model_validate(new))
                )
                kind = "host_group"
            case ObjectType.GROUPS:
                await sync.handle_group_modify(
                    GroupModifyEvent(**meta, new=GroupPayload.model_validate(new))
                )
                kind = "group"
            case ObjectType.OUS:
                await sync.handle_school_modify(
                    SchoolModifyEvent(**meta, new=SchoolPayload.model_validate(new))
                )
                kind = "school"
            case _:
                return self._skip_unknown_type("modify", task)
        self._log_processed("Modify", kind, new, task["seq_number"])
        return Outcome(OutcomeKind.MODIFIED)

    async def _remove(self, task: Task) -> Outcome:
        # Deletion only needs the identifier: the rest of a deleted object's
        # state may be malformed and must not prevent removing it from the
        # cache (see DeletePayload).
        old = task["old"]
        meta = {"timestamp": task["ts"], "sequence_number": task["seq_number"]}
        sync = self.synchronization_manager
        match task["udm_module"]:
            case ObjectType.USERS:
                await sync.handle_user_delete(
                    UserDeleteEvent(**meta, old=DeletePayload.model_validate(old))
                )
                kind = "user"
            case ObjectType.GROUPS if HOST_GROUP_NAME_RE.match(old["properties"].get("name", "")):
                await sync.handle_host_group_delete(
                    HostGroupDeleteEvent(**meta, old=HostGroupPayload.model_validate(old))
                )
                kind = "host_group"
            case ObjectType.GROUPS:
                await sync.handle_group_delete(
                    GroupDeleteEvent(**meta, old=DeletePayload.model_validate(old))
                )
                kind = "group"
            case ObjectType.OUS:
                await sync.handle_school_delete(
                    SchoolDeleteEvent(**meta, old=DeletePayload.model_validate(old))
                )
                kind = "school"
            case _:
                return self._skip_unknown_type("delete", task)
        self._log_processed("Delete", kind, old, task["seq_number"])
        return Outcome(OutcomeKind.DELETED)


class TaskRunner:
    """The synchronous side of the callback, called by the CCF per task."""

    def __init__(
        self, loop_thread: CoroutineRunnerProtocol, processor: TaskProcessor, timeout: float
    ) -> None:
        self._loop_thread: CoroutineRunnerProtocol = loop_thread
        self._processor: TaskProcessor = processor
        self._timeout: float = timeout

    def __call__(self, task: Task) -> Outcome:
        # The loop thread does not inherit this thread's context, so
        # TaskProcessor.process sets the request_id there again.
        with logger.contextualize(request_id=task["request_id"]):
            if not is_relevant(task):
                return Outcome(OutcomeKind.SKIPPED)
            try:
                return self._loop_thread.run(self._processor.process(task), self._timeout)
            except TimeoutError:
                msg = f"processing did not finish within {self._timeout}s"
                logger.error("Event {} failed: {}", task["seq_number"], msg)
                return Outcome(OutcomeKind.FAILURE, msg)
            except Exception as exc:
                logger.opt(exception=exc).error("Event {} failed", task["seq_number"])
                return Outcome(OutcomeKind.FAILURE, f"{type(exc).__name__}: {exc}")


def to_callback_result(callback_result: Any, outcome: Outcome) -> Any:
    """Map an outcome onto the `CallbackResult` class the CCF injected."""
    match outcome.kind:
        case OutcomeKind.CREATED:
            return callback_result.SuccessCreated()
        case OutcomeKind.MODIFIED:
            return callback_result.SuccessModified()
        case OutcomeKind.DELETED:
            return callback_result.SuccessDeleted
        case OutcomeKind.SKIPPED:
            return callback_result.SuccessSkipped
        case OutcomeKind.FAILURE:
            return callback_result.Failure(outcome.msg)
        case OutcomeKind.PERMANENT_FAILURE:  # pragma: no branch (the match is exhaustive)
            return callback_result.PermanentFailure(outcome.msg)
