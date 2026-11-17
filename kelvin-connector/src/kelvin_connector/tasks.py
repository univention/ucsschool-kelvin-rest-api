# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
"""Process CCF tasks: decide relevance, dispatch to the synchronization manager.

The task only uses what CCF offers anyway:

- ``task["attrs"]`` is ``{"dn": …, "properties": …}`` (rendered by the
  ``ccf_templates/provisioning`` templates from the message's ``new`` side,
  the DN as sent) on a create or modify, and ``{}`` on a delete.
- A delete needs only the task's ``obj_id`` (the ``univentionObjectIdentifier``)
  and ``dn``, never CCF's ``old`` table: objects synced before the CCF had an
  ``old`` row (an upgrade keeps the subscription), or whose create task was
  replaced by the delete or ended in the morgue, must still be deleted.
- Whether the object of a create or modify task is new or known comes from
  CCF's ``old`` table (``consumer.get_old``). On success the callback trims
  ``task["attrs"]`` down to a few identifying properties, which is what CCF
  then stores in ``old``.
"""

from __future__ import annotations

import enum
import logging
import re
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass
from typing import Protocol, TypedDict, cast

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

from .dn import rdns
from .log import request_id_context
from .ports import CoroutineRunnerProtocol, SynchronizationManagerProtocol

logger = logging.getLogger(__name__)

# Case-insensitive like the cn itself: on a delete, the name is taken from the
# CCF's normalized (lower case) DN.
HOST_GROUP_NAME_RE = re.compile(r"OU(.*)-DC-(Edukativnetz|Verwaltungsnetz)", re.IGNORECASE)

# The properties kept in CCF's `old` table. Only the row's existence is used
# (create or modify); the properties identify the object for an admin.
OLD_STATE_PROPERTIES = ("univentionObjectIdentifier", "name", "username")

# `{"dn": …, "properties": …}` as parsed JSON. Only read here; the Pydantic
# models in models.py validate it.
Payload = Mapping[str, object]


class Task(TypedDict):
    """The keys of a CCF task dict this module uses (see the CCF README)."""

    obj_id: str
    udm_module: str
    dn: str
    request_id: str
    attrs: dict[str, object]


class OldRow(TypedDict):
    attrs: dict[str, object]


class ConsumerProtocol(Protocol):  # pragma: no cover
    """The read-only CCF state handed to the callback."""

    def get_old(self, obj_id: str) -> OldRow | None: ...


class CallbackResultClass(Protocol):  # pragma: no cover
    """The `CallbackResult` class the CCF adds to the callback module."""

    @property
    def SuccessDeleted(self) -> object: ...

    @property
    def SuccessSkipped(self) -> object: ...

    def SuccessCreated(self) -> object: ...

    def SuccessModified(self) -> object: ...

    def Failure(self, msg: str | None) -> object: ...


class ObjectType(enum.StrEnum):
    USERS = "users/user"
    GROUPS = "groups/group"
    OUS = "container/ou"


OBJECT_TYPES = frozenset(object_type.value for object_type in ObjectType)


class OutcomeKind(enum.Enum):
    CREATED = enum.auto()
    MODIFIED = enum.auto()
    DELETED = enum.auto()
    SKIPPED = enum.auto()
    FAILURE = enum.auto()


@dataclass(frozen=True)
class Outcome:
    kind: OutcomeKind
    msg: str | None = None


def _properties(payload: Payload) -> Mapping[str, object]:
    properties = payload.get("properties")
    return cast("dict[str, object]", properties) if isinstance(properties, dict) else {}


def _name(payload: Payload) -> str:
    return str(_properties(payload).get("name", ""))


def _roles(properties: Mapping[str, object]) -> list[str]:
    roles = properties.get("ucsschoolRole")
    return [str(role) for role in cast("list[object]", roles)] if isinstance(roles, list) else []


def is_relevant(udm_module: str, payload: Payload) -> bool:
    """Whether the Kelvin DB caches the object `payload` describes."""
    properties = _properties(payload)
    name = str(properties.get("name", ""))
    if "ucsschoolRole" not in properties:
        logger.info("Skipping: no ucsschoolRole in the UDM properties, udm_module=%s", udm_module)
        return False
    roles = _roles(properties)
    match udm_module:
        case ObjectType.GROUPS:
            if any(role.startswith(("school_class", "workgroup")) for role in roles):
                return True
            if HOST_GROUP_NAME_RE.match(name):
                return True
            logger.info(
                "Skipping: not a school class, work group or host group, name=%s",
                name,
            )
            return False
        case ObjectType.USERS:
            # Exam users are temporary copies (created under cn=examusers
            # for the duration of an exam, then deleted). They are
            # intentionally not cached.
            if any(role.startswith("exam_user:") for role in roles):
                logger.info("Skipping: exam user, name=%s", name)
                return False
            return True
        case _:  # ObjectType.OUS; other types are skipped before
            return True


def old_state(payload: Payload) -> dict[str, object]:
    """The part of `payload` CCF keeps in `old`."""
    properties = _properties(payload)
    return {
        "dn": payload.get("dn", ""),
        "properties": {key: properties[key] for key in OLD_STATE_PROPERTIES if key in properties},
    }


def _leaf_value(dn: str) -> str:
    """The value of the leaf RDN of `dn`, or "" for a malformed DN."""
    try:
        return rdns(dn)[0][1]
    except (ValueError, IndexError):
        return ""


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

    @staticmethod
    def _log_processed(operation: str, kind: str, payload: Payload) -> None:
        logger.info(
            "%s %s event processed: dn=%s, public_id=%s",
            operation,
            kind,
            payload.get("dn", ""),
            _properties(payload).get("univentionObjectIdentifier", ""),
        )

    async def create(self, udm_module: str, new: Payload) -> Outcome:
        sync = self.synchronization_manager
        match udm_module:
            case ObjectType.USERS:
                await sync.handle_user_create(UserCreateEvent(new=UserPayload.model_validate(new)))
                kind = "user"
            case ObjectType.GROUPS if HOST_GROUP_NAME_RE.match(_name(new)):
                await sync.handle_host_group_create(
                    HostGroupCreateEvent(new=HostGroupPayload.model_validate(new))
                )
                kind = "host_group"
            case ObjectType.GROUPS:
                await sync.handle_group_create(GroupCreateEvent(new=GroupPayload.model_validate(new)))
                kind = "group"
            case _:  # ObjectType.OUS; other types are skipped before
                await sync.handle_school_create(SchoolCreateEvent(new=SchoolPayload.model_validate(new)))
                kind = "school"
        self._log_processed("Create", kind, new)
        return Outcome(OutcomeKind.CREATED)

    async def modify(self, udm_module: str, new: Payload) -> Outcome:
        # A move or rename needs no special handling: the modify handlers
        # refresh the DN mapping from the event's new dn unconditionally.
        sync = self.synchronization_manager
        match udm_module:
            case ObjectType.USERS:
                await sync.handle_user_modify(UserModifyEvent(new=UserPayload.model_validate(new)))
                kind = "user"
            case ObjectType.GROUPS if HOST_GROUP_NAME_RE.match(_name(new)):
                await sync.handle_host_group_modify(
                    HostGroupModifyEvent(new=HostGroupPayload.model_validate(new))
                )
                kind = "host_group"
            case ObjectType.GROUPS:
                await sync.handle_group_modify(GroupModifyEvent(new=GroupPayload.model_validate(new)))
                kind = "group"
            case _:  # ObjectType.OUS; other types are skipped before
                await sync.handle_school_modify(SchoolModifyEvent(new=SchoolPayload.model_validate(new)))
                kind = "school"
        self._log_processed("Modify", kind, new)
        return Outcome(OutcomeKind.MODIFIED)

    async def delete(self, udm_module: str, obj_id: str, dn: str) -> Outcome:
        # A delete task has no properties: the object ID is the identifier,
        # and a DC host group (not an object in the Kelvin DB) is recognized
        # by the leaf cn of its DN. Deleting an object that is not in the
        # Kelvin DB (never synced or irrelevant) is a no-op.
        sync = self.synchronization_manager
        old: dict[str, object] = {"dn": dn, "properties": {"univentionObjectIdentifier": obj_id}}
        name = _leaf_value(dn)
        match udm_module:
            case ObjectType.USERS:
                await sync.handle_user_delete(UserDeleteEvent(old=DeletePayload.model_validate(old)))
                kind = "user"
            case ObjectType.GROUPS if HOST_GROUP_NAME_RE.match(name):
                old["properties"] = {"univentionObjectIdentifier": obj_id, "name": name}
                await sync.handle_host_group_delete(
                    HostGroupDeleteEvent(old=DeletePayload.model_validate(old))
                )
                kind = "host_group"
            case ObjectType.GROUPS:
                await sync.handle_group_delete(GroupDeleteEvent(old=DeletePayload.model_validate(old)))
                kind = "group"
            case _:  # ObjectType.OUS; other types are skipped before
                await sync.handle_school_delete(SchoolDeleteEvent(old=DeletePayload.model_validate(old)))
                kind = "school"
        self._log_processed("Delete", kind, old)
        return Outcome(OutcomeKind.DELETED)


class TaskRunner:
    """The synchronous side of the callback, called by the CCF per task."""

    def __init__(
        self, loop_thread: CoroutineRunnerProtocol, processor: TaskProcessor, timeout: float
    ) -> None:
        self.loop_thread: CoroutineRunnerProtocol = loop_thread
        self.processor: TaskProcessor = processor
        self.timeout: float = timeout

    def __call__(self, consumer: ConsumerProtocol, task: Task) -> Outcome:
        # The CCF logs this thread's lines with the task's request ID itself.
        try:
            return self._run(consumer, task)
        except ValidationError as exc:
            # Retrying cannot fix invalid data, but CCF's error limit moves
            # the task to the morgue after a few attempts anyway.
            summary = _validation_summary(exc)
            logger.error("Object %s is malformed: %s", task["obj_id"], summary)
            return Outcome(OutcomeKind.FAILURE, summary)
        except TimeoutError:
            msg = f"processing did not finish within {self.timeout}s"
            logger.error("Object %s failed: %s", task["obj_id"], msg)
            return Outcome(OutcomeKind.FAILURE, msg)
        except Exception as exc:
            logger.exception("Object %s failed", task["obj_id"])
            return Outcome(OutcomeKind.FAILURE, f"{type(exc).__name__}: {exc}")

    def _run(self, consumer: ConsumerProtocol, task: Task) -> Outcome:
        udm_module = task["udm_module"]
        if udm_module not in OBJECT_TYPES:
            logger.info("Skipping object %s: unknown udm_module %s", task["obj_id"], udm_module)
            return Outcome(OutcomeKind.SKIPPED)
        new = task["attrs"]
        if not new:
            # Independent of CCF's `old` table (see the module docstring).
            return self._on_loop(task, self.processor.delete(udm_module, task["obj_id"], task["dn"]))
        if not is_relevant(udm_module, new):
            return Outcome(OutcomeKind.SKIPPED)
        if consumer.get_old(task["obj_id"]) is None:
            outcome = self._on_loop(task, self.processor.create(udm_module, new))
        else:
            outcome = self._on_loop(task, self.processor.modify(udm_module, new))
        # CCF stores the attrs left in the task as the object's `old` row.
        task["attrs"] = old_state(new)
        return outcome

    def _on_loop(self, task: Task, coro: Coroutine[object, object, Outcome]) -> Outcome:
        return self.loop_thread.run(_with_request_id(task["request_id"], coro), self.timeout)


async def _with_request_id(request_id: str, coro: Coroutine[object, object, Outcome]) -> Outcome:
    # The loop thread does not inherit the calling thread's context, and the
    # CCF does not know which task a line logged there belongs to.
    with request_id_context(request_id):
        return await coro


def to_callback_result(callback_result: CallbackResultClass, outcome: Outcome) -> object:
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
        case OutcomeKind.FAILURE:  # pragma: no branch (the match is exhaustive)
            return callback_result.Failure(outcome.msg)
