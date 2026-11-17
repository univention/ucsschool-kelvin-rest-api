# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, ClassVar, TypeVar
from unittest.mock import AsyncMock, MagicMock

import pytest
from kelvin_connector.log import install_request_id_record_factory
from kelvin_connector.loop_thread import AsyncioLoopThread
from kelvin_connector.models import (
    GroupCreateEvent,
    GroupDeleteEvent,
    GroupModifyEvent,
    HostGroupCreateEvent,
    HostGroupDeleteEvent,
    HostGroupModifyEvent,
    SchoolCreateEvent,
    SchoolDeleteEvent,
    SchoolModifyEvent,
    UserCreateEvent,
    UserDeleteEvent,
    UserModifyEvent,
)
from kelvin_connector.tasks import (
    OldRow,
    Outcome,
    OutcomeKind,
    Task,
    TaskProcessor,
    TaskRunner,
    is_relevant,
    old_state,
    to_callback_result,
)
from typing_extensions import override

T = TypeVar("T")


def _uid() -> str:
    return str(uuid.uuid4())


# The attrs the ccf_templates/provisioning templates render: the DN as sent
# and the message's `new.properties`.


def _user_payload(uid: str | None = None) -> dict[str, Any]:
    return {
        "dn": "uid=testuser,cn=users,ou=TestSchool,dc=test",
        "properties": {
            "univentionObjectIdentifier": uid or _uid(),
            "username": "testuser",
            "firstname": "Test",
            "lastname": "User",
            "disabled": False,
            "school": ["testschool"],
            "ucsschoolRole": ["teacher:school:testschool"],
            "ucsschoolRecordUID": "testuser",
            "ucsschoolSourceUID": "src",
            "groups": [],
            "ucsschoolLegalWard": [],
            "ucsschoolLegalGuardian": [],
            "mailPrimaryAddress": "",
        },
    }


def _group_payload(uid: str | None = None) -> dict[str, Any]:
    return {
        "dn": "cn=testgroup,cn=klassen,dc=test",
        "properties": {
            "univentionObjectIdentifier": uid or _uid(),
            "name": "testgroup",
            "ucsschoolRole": ["school_class:school:testschool"],
            "allowedEmailUsers": [],
            "allowedEmailGroups": [],
            "users": [],
            "mailAddress": None,
            "guardianMemberRoles": [],
        },
    }


def _host_group_payload(uid: str | None = None) -> dict[str, Any]:
    return {
        "dn": "cn=OUdemoschool-DC-Edukativnetz,cn=ucsschool,cn=groups,dc=test",
        "properties": {
            "univentionObjectIdentifier": uid or _uid(),
            "name": "OUdemoschool-DC-Edukativnetz",
            "description": "DC host group for demoschool",
            "ucsschoolRole": [],
            "hosts": ["cn=dc1,cn=dc,cn=computers,ou=demoschool,dc=test"],
        },
    }


def _school_payload(uid: str | None = None) -> dict[str, Any]:
    return {
        "dn": "ou=TestSchool,dc=test",
        "properties": {
            "univentionObjectIdentifier": uid or _uid(),
            "name": "TestSchool",
            "displayName": "testschool Display",
            "ucsschoolRole": ["school:school:TestSchool"],
        },
    }


Payload = Callable[..., dict[str, Any]]

PAYLOADS = [
    pytest.param("users/user", _user_payload, "user", id="user"),
    pytest.param("groups/group", _group_payload, "group", id="group"),
    pytest.param("groups/group", _host_group_payload, "host_group", id="host_group"),
    pytest.param("container/ou", _school_payload, "school", id="school"),
]


def _task(
    udm_module: str,
    attrs: dict[str, Any] | None = None,
    obj_id: str = "obj-1",
    dn: str = "cn=x,dc=test",
) -> Task:
    """The keys of a CCF task dict the callback uses."""
    return {
        "obj_id": obj_id,
        "udm_module": udm_module,
        "dn": dn,
        "request_id": "req-1",
        "attrs": attrs or {},
    }


def _roles(*roles: str, name: str = "") -> dict[str, Any]:
    return {"dn": "cn=x", "properties": {"ucsschoolRole": list(roles), "name": name}}


class _Consumer:
    """The CCF consumer with an in-memory `old` table."""

    def __init__(self, old: dict[str, Any] | None = None, exc: Exception | None = None) -> None:
        self.old: dict[str, Any] | None = old
        self.exc: Exception | None = exc
        self.calls: list[str] = []

    def get_old(self, obj_id: str) -> OldRow | None:
        self.calls.append(obj_id)
        if self.exc:
            raise self.exc
        return None if self.old is None else {"attrs": self.old}


# ── is_relevant / old_state ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "udm_module, payload",
    [
        pytest.param("users/user", _roles("teacher:school:DEMOSCHOOL"), id="user"),
        pytest.param("container/ou", _roles("school_admin:school:DEMOSCHOOL"), id="ou"),
        pytest.param("groups/group", _roles("school_class:school:DEMOSCHOOL"), id="school_class"),
        pytest.param("groups/group", _roles("workgroup:school:DEMOSCHOOL"), id="workgroup"),
        pytest.param(
            "groups/group",
            _roles("other:school:DEMOSCHOOL", name="OUdemo-DC-Verwaltungsnetz"),
            id="host_group",
        ),
    ],
)
def test_is_relevant_accepts_school_objects(udm_module: str, payload: dict[str, Any]) -> None:
    assert is_relevant(udm_module, payload) is True


@pytest.mark.parametrize(
    "udm_module, payload",
    [
        pytest.param("users/user", {"dn": "cn=x"}, id="no_properties"),
        pytest.param("users/user", {"dn": "cn=x", "properties": {}}, id="no_ucsschool_role"),
        pytest.param(
            "groups/group",
            {"dn": "cn=x", "properties": {"ucsschoolRole": "not-a-list"}},
            id="malformed_roles",
        ),
        pytest.param(
            "users/user",
            _roles("exam_user:school:DEMOSCHOOL", "exam_user:exam:demo-DEMOSCHOOL"),
            id="exam_user",
        ),
        pytest.param("groups/group", _roles("other_role:school:DEMOSCHOOL"), id="other_group"),
    ],
)
def test_is_relevant_skips_other_objects(udm_module: str, payload: dict[str, Any]) -> None:
    assert is_relevant(udm_module, payload) is False


def test_old_state_keeps_only_identifying_properties() -> None:
    payload = _user_payload("2b1c1b4e-0f5e-4d47-9a2a-1b2c3d4e5f60")

    assert old_state(payload) == {
        "dn": payload["dn"],
        "properties": {
            "univentionObjectIdentifier": "2b1c1b4e-0f5e-4d47-9a2a-1b2c3d4e5f60",
            "username": "testuser",
        },
    }


def test_old_state_of_a_payload_without_properties() -> None:
    assert old_state({}) == {"dn": "", "properties": {}}


# ── TaskProcessor ─────────────────────────────────────────────────────────────


@pytest.fixture
def sync_manager() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def processor(sync_manager: AsyncMock) -> TaskProcessor:
    return TaskProcessor(sync_manager)


@pytest.mark.parametrize(
    "udm_module, payload, handler, event_cls",
    [
        ("users/user", _user_payload, "handle_user_create", UserCreateEvent),
        ("groups/group", _group_payload, "handle_group_create", GroupCreateEvent),
        ("groups/group", _host_group_payload, "handle_host_group_create", HostGroupCreateEvent),
        ("container/ou", _school_payload, "handle_school_create", SchoolCreateEvent),
    ],
)
async def test_process_create(
    processor: TaskProcessor,
    sync_manager: AsyncMock,
    udm_module: str,
    payload: Payload,
    handler: str,
    event_cls: type,
) -> None:
    new = payload()

    assert await processor.create(udm_module, new) == Outcome(OutcomeKind.CREATED)

    (event,), _ = getattr(sync_manager, handler).call_args
    assert isinstance(event, event_cls)
    assert event.new.dn == new["dn"], "the DN is passed as sent, not normalized"


@pytest.mark.parametrize(
    "udm_module, payload, handler, event_cls",
    [
        ("users/user", _user_payload, "handle_user_modify", UserModifyEvent),
        ("groups/group", _group_payload, "handle_group_modify", GroupModifyEvent),
        ("groups/group", _host_group_payload, "handle_host_group_modify", HostGroupModifyEvent),
        ("container/ou", _school_payload, "handle_school_modify", SchoolModifyEvent),
    ],
)
async def test_process_modify(
    processor: TaskProcessor,
    sync_manager: AsyncMock,
    udm_module: str,
    payload: Payload,
    handler: str,
    event_cls: type,
) -> None:
    uid = _uid()

    assert await processor.modify(udm_module, payload(uid)) == Outcome(OutcomeKind.MODIFIED)

    (event,), _ = getattr(sync_manager, handler).call_args
    assert isinstance(event, event_cls)
    assert str(event.new.properties.univentionObjectIdentifier) == uid


@pytest.mark.parametrize(
    "udm_module, payload, handler, event_cls",
    [
        ("users/user", _user_payload, "handle_user_delete", UserDeleteEvent),
        ("groups/group", _group_payload, "handle_group_delete", GroupDeleteEvent),
        ("groups/group", _host_group_payload, "handle_host_group_delete", HostGroupDeleteEvent),
        ("container/ou", _school_payload, "handle_school_delete", SchoolDeleteEvent),
    ],
)
async def test_process_delete_from_the_object_id_and_dn(
    processor: TaskProcessor,
    sync_manager: AsyncMock,
    udm_module: str,
    payload: Payload,
    handler: str,
    event_cls: type,
) -> None:
    uid = _uid()
    # The CCF hands over the normalized (lower case) DN.
    dn = payload()["dn"].lower()

    outcome = await processor.delete(udm_module, uid, dn)

    assert outcome == Outcome(OutcomeKind.DELETED)
    (event,), _ = getattr(sync_manager, handler).call_args
    assert isinstance(event, event_cls)
    assert str(event.old.properties.univentionObjectIdentifier) == uid
    assert event.old.dn == dn


async def test_process_delete_of_a_host_group_takes_the_name_from_the_dn(
    processor: TaskProcessor, sync_manager: AsyncMock
) -> None:
    dn = "cn=oudemoschool-dc-verwaltungsnetz,cn=ucsschool,cn=groups,dc=test"

    assert await processor.delete("groups/group", _uid(), dn) == Outcome(OutcomeKind.DELETED)

    (event,), _ = sync_manager.handle_host_group_delete.call_args
    assert event.old.properties.name == "oudemoschool-dc-verwaltungsnetz"
    sync_manager.handle_group_delete.assert_not_awaited()


async def test_process_delete_of_a_group_with_a_malformed_dn(
    processor: TaskProcessor, sync_manager: AsyncMock
) -> None:
    assert await processor.delete("groups/group", _uid(), "not a dn") == Outcome(OutcomeKind.DELETED)

    sync_manager.handle_group_delete.assert_awaited_once()
    sync_manager.handle_host_group_delete.assert_not_awaited()


# ── TaskRunner ────────────────────────────────────────────────────────────────


class _InlineLoopThread:
    """Runs the coroutine right away instead of on a separate loop thread."""

    def __init__(self, exc: Exception | None = None) -> None:
        self.exc: Exception | None = exc
        self.timeouts: list[float | None] = []

    def run(self, coro: Coroutine[object, object, T], timeout: float | None = None) -> T:
        self.timeouts.append(timeout)
        if self.exc:
            coro.close()
            raise self.exc
        return asyncio.run(coro)


def _runner(sync_manager: AsyncMock | None = None, exc: Exception | None = None) -> TaskRunner:
    return TaskRunner(
        _InlineLoopThread(exc),
        TaskProcessor(AsyncMock() if sync_manager is None else sync_manager),
        timeout=10,
    )


@pytest.mark.parametrize("udm_module, payload, kind", PAYLOADS)
def test_runner_creates_an_unknown_object_and_keeps_its_old_state(
    udm_module: str, payload: Payload, kind: str
) -> None:
    sync_manager = AsyncMock()
    new = payload()
    task = _task(udm_module, new)

    assert _runner(sync_manager)(_Consumer(), task) == Outcome(OutcomeKind.CREATED)

    getattr(sync_manager, f"handle_{kind}_create").assert_awaited_once()
    assert task["attrs"] == old_state(new), "CCF stores these attrs in `old`"


@pytest.mark.parametrize("udm_module, payload, kind", PAYLOADS)
def test_runner_modifies_a_known_object(udm_module: str, payload: Payload, kind: str) -> None:
    sync_manager = AsyncMock()
    uid = _uid()
    task = _task(udm_module, payload(uid))

    outcome = _runner(sync_manager)(_Consumer(old=old_state(payload(uid))), task)

    assert outcome == Outcome(OutcomeKind.MODIFIED)
    getattr(sync_manager, f"handle_{kind}_modify").assert_awaited_once()


@pytest.mark.parametrize("udm_module, payload, kind", PAYLOADS)
def test_runner_deletes_without_reading_old(udm_module: str, payload: Payload, kind: str) -> None:
    # Objects without an `old` row (synced before the CCF, or whose create
    # task never succeeded) must be deleted, too.
    sync_manager = AsyncMock()
    consumer = _Consumer()
    uid = _uid()
    task = _task(udm_module, obj_id=uid, dn=payload()["dn"].lower())

    assert _runner(sync_manager)(consumer, task) == Outcome(OutcomeKind.DELETED)

    (event,), _ = getattr(sync_manager, f"handle_{kind}_delete").call_args
    assert str(event.old.properties.univentionObjectIdentifier) == uid
    assert consumer.calls == []


def test_runner_reports_a_delete_with_a_malformed_object_id_as_failure() -> None:
    sync_manager = AsyncMock()

    outcome = _runner(sync_manager)(_Consumer(), _task("users/user", obj_id="not-a-uuid"))

    assert outcome.kind is OutcomeKind.FAILURE
    sync_manager.handle_user_delete.assert_not_awaited()


def test_runner_skips_irrelevant_objects_without_using_the_loop() -> None:
    loop_thread = MagicMock()
    task = _task("groups/group", _roles("other_role:school:X"))
    attrs = dict(task["attrs"])

    outcome = TaskRunner(loop_thread, MagicMock(), timeout=10)(_Consumer(), task)

    assert outcome == Outcome(OutcomeKind.SKIPPED)
    loop_thread.run.assert_not_called()
    assert task["attrs"] == attrs


def test_runner_skips_unknown_object_types_without_reading_old() -> None:
    consumer = _Consumer()

    outcome = _runner()(consumer, _task("unknown/type", {"dn": "cn=x", "properties": {}}))

    assert outcome == Outcome(OutcomeKind.SKIPPED)
    assert consumer.calls == []


def test_runner_reports_invalid_data_as_failure_without_values() -> None:
    sync_manager = AsyncMock()
    new = _user_payload()
    new["properties"]["birthday"] = "secret-not-a-date"

    outcome = _runner(sync_manager)(_Consumer(), _task("users/user", new))

    assert outcome.kind is OutcomeKind.FAILURE
    assert outcome.msg is not None
    assert "properties.birthday" in outcome.msg
    assert "secret-not-a-date" not in outcome.msg
    sync_manager.handle_user_create.assert_not_awaited()


def test_runner_passes_the_timeout_to_the_loop() -> None:
    loop_thread = _InlineLoopThread()
    runner = TaskRunner(loop_thread, TaskProcessor(AsyncMock()), timeout=10)

    runner(_Consumer(), _task("users/user", _user_payload()))

    assert loop_thread.timeouts == [10]


def test_runner_logs_with_the_request_id_on_the_loop_thread() -> None:
    loop_thread = AsyncioLoopThread()
    loop_thread.start()
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        @override
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Collect()
    task_logger = logging.getLogger("kelvin_connector.tasks")
    task_logger.addHandler(handler)
    task_logger.setLevel(logging.INFO)
    record_factory = logging.getLogRecordFactory()
    install_request_id_record_factory()
    try:
        runner = TaskRunner(loop_thread, TaskProcessor(AsyncMock()), timeout=10)
        assert runner(_Consumer(), _task("users/user", _user_payload())) == Outcome(OutcomeKind.CREATED)
    finally:
        logging.setLogRecordFactory(record_factory)
        task_logger.setLevel(logging.NOTSET)
        task_logger.removeHandler(handler)
        loop_thread.stop()

    on_loop = [record for record in records if record.threadName == "kelvin-connector-loop"]
    assert on_loop
    assert all(getattr(record, "request_id", None) == "req-1" for record in on_loop)
    # The CCF knows the request ID of its own threads.
    assert all(not hasattr(record, "request_id") for record in records if record not in on_loop)


def test_runner_reports_a_timeout_as_failure() -> None:
    outcome = _runner(exc=TimeoutError())(_Consumer(), _task("users/user", _user_payload()))

    assert outcome == Outcome(OutcomeKind.FAILURE, "processing did not finish within 10s")


def test_runner_reports_other_errors_as_failure() -> None:
    outcome = _runner(exc=RuntimeError("db down"))(_Consumer(), _task("users/user", _user_payload()))

    assert outcome == Outcome(OutcomeKind.FAILURE, "RuntimeError: db down")


def test_runner_reports_an_unreadable_old_table_as_failure() -> None:
    task = _task("users/user", _user_payload())

    outcome = _runner()(_Consumer(exc=OSError("ccf db down")), task)

    assert outcome == Outcome(OutcomeKind.FAILURE, "OSError: ccf db down")


# ── to_callback_result ────────────────────────────────────────────────────────


class _FakeCallbackResult:
    """Mirrors the CCF's CallbackResult: class attributes and classmethods."""

    SuccessDeleted: ClassVar[str] = "SuccessDeleted"
    SuccessSkipped: ClassVar[str] = "SuccessSkipped"

    @classmethod
    def SuccessCreated(cls) -> str:
        return "SuccessCreated"

    @classmethod
    def SuccessModified(cls) -> str:
        return "SuccessModified"

    @classmethod
    def Failure(cls, msg: str | None) -> tuple[str, str | None]:
        return ("Failure", msg)


@pytest.mark.parametrize(
    "outcome, expected",
    [
        (Outcome(OutcomeKind.CREATED), "SuccessCreated"),
        (Outcome(OutcomeKind.MODIFIED), "SuccessModified"),
        (Outcome(OutcomeKind.DELETED), "SuccessDeleted"),
        (Outcome(OutcomeKind.SKIPPED), "SuccessSkipped"),
        (Outcome(OutcomeKind.FAILURE, "boom"), ("Failure", "boom")),
    ],
)
def test_to_callback_result_maps_every_outcome(outcome: Outcome, expected: object) -> None:
    assert to_callback_result(_FakeCallbackResult, outcome) == expected
