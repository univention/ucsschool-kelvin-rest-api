# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest
from ccf import CallbackResult, CcfDatabaseError, Consumer, Old, Task
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
    TaskProcessor,
    TaskRunner,
    is_relevant,
    old_state,
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
    return {
        "id": 1,
        "obj_id": obj_id,
        "udm_module": udm_module,
        "dn": dn,
        "attrs": attrs or {},
        "status": "new",
        "num_errors": 0,
        "request_id": "req-1",
        "delay": 0,
    }


def _roles(*roles: str, name: str = "") -> dict[str, Any]:
    return {"dn": "cn=x", "properties": {"ucsschoolRole": list(roles), "name": name}}


def _consumer(old: dict[str, Any] | None = None, exc: Exception | None = None) -> MagicMock:
    """The CCF consumer with the `old` row `old`; only `get_old` is used."""
    consumer = create_autospec(Consumer, instance=True)
    if exc is not None:
        consumer.get_old.side_effect = exc
    elif old is not None:
        row: Old = {
            "id": 1,
            "obj_id": "",
            "udm_module": "",
            "dn": "",
            "attrs": old,
            "request_id": "req-0",
        }
        consumer.get_old.return_value = row
    else:
        consumer.get_old.return_value = None
    return consumer


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

    assert await processor.create(udm_module, new) == CallbackResult.SuccessCreated()

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

    assert await processor.modify(udm_module, payload(uid)) == CallbackResult.SuccessModified()

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

    result = await processor.delete(udm_module, uid, dn)

    assert result == CallbackResult.SuccessDeleted
    (event,), _ = getattr(sync_manager, handler).call_args
    assert isinstance(event, event_cls)
    assert str(event.old.properties.univentionObjectIdentifier) == uid
    assert event.old.dn == dn


async def test_process_delete_of_a_host_group_takes_the_name_from_the_dn(
    processor: TaskProcessor, sync_manager: AsyncMock
) -> None:
    dn = "cn=oudemoschool-dc-verwaltungsnetz,cn=ucsschool,cn=groups,dc=test"

    assert await processor.delete("groups/group", _uid(), dn) == CallbackResult.SuccessDeleted

    (event,), _ = sync_manager.handle_host_group_delete.call_args
    assert event.old.properties.name == "oudemoschool-dc-verwaltungsnetz"
    sync_manager.handle_group_delete.assert_not_awaited()


async def test_process_delete_of_a_group_with_a_malformed_dn(
    processor: TaskProcessor, sync_manager: AsyncMock
) -> None:
    assert await processor.delete("groups/group", _uid(), "not a dn") == CallbackResult.SuccessDeleted

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

    assert _runner(sync_manager)(_consumer(), task) == CallbackResult.SuccessCreated()

    getattr(sync_manager, f"handle_{kind}_create").assert_awaited_once()
    assert task["attrs"] == old_state(new), "CCF stores these attrs in `old`"


@pytest.mark.parametrize("udm_module, payload, kind", PAYLOADS)
def test_runner_modifies_a_known_object(udm_module: str, payload: Payload, kind: str) -> None:
    sync_manager = AsyncMock()
    uid = _uid()
    task = _task(udm_module, payload(uid))

    result = _runner(sync_manager)(_consumer(old=old_state(payload(uid))), task)

    assert result == CallbackResult.SuccessModified()
    getattr(sync_manager, f"handle_{kind}_modify").assert_awaited_once()


@pytest.mark.parametrize("udm_module, payload, kind", PAYLOADS)
def test_runner_deletes_without_reading_old(udm_module: str, payload: Payload, kind: str) -> None:
    # Objects without an `old` row (synced before the CCF, or whose create
    # task never succeeded) must be deleted, too.
    sync_manager = AsyncMock()
    consumer = _consumer()
    uid = _uid()
    task = _task(udm_module, obj_id=uid, dn=payload()["dn"].lower())

    assert _runner(sync_manager)(consumer, task) == CallbackResult.SuccessDeleted

    (event,), _ = getattr(sync_manager, f"handle_{kind}_delete").call_args
    assert str(event.old.properties.univentionObjectIdentifier) == uid
    consumer.get_old.assert_not_called()


def test_runner_reports_a_delete_with_a_malformed_object_id_as_failure() -> None:
    sync_manager = AsyncMock()

    result = _runner(sync_manager)(_consumer(), _task("users/user", obj_id="not-a-uuid"))

    assert result.kind == "Failure"
    sync_manager.handle_user_delete.assert_not_awaited()


def test_runner_skips_irrelevant_objects_without_using_the_loop() -> None:
    loop_thread = MagicMock()
    task = _task("groups/group", _roles("other_role:school:X"))
    attrs = dict(task["attrs"])

    result = TaskRunner(loop_thread, MagicMock(), timeout=10)(_consumer(), task)

    assert result == CallbackResult.SuccessSkipped
    loop_thread.run.assert_not_called()
    assert task["attrs"] == attrs


def test_runner_skips_unknown_object_types_without_reading_old() -> None:
    consumer = _consumer()

    result = _runner()(consumer, _task("unknown/type", {"dn": "cn=x", "properties": {}}))

    assert result == CallbackResult.SuccessSkipped
    consumer.get_old.assert_not_called()


def test_runner_reports_invalid_data_as_failure_without_values() -> None:
    sync_manager = AsyncMock()
    new = _user_payload()
    new["properties"]["birthday"] = "secret-not-a-date"

    result = _runner(sync_manager)(_consumer(), _task("users/user", new))

    assert result.kind == "Failure"
    assert result.msg is not None
    assert "properties.birthday" in result.msg
    assert "secret-not-a-date" not in result.msg
    sync_manager.handle_user_create.assert_not_awaited()


def test_runner_passes_the_timeout_to_the_loop() -> None:
    loop_thread = _InlineLoopThread()
    runner = TaskRunner(loop_thread, TaskProcessor(AsyncMock()), timeout=10)

    runner(_consumer(), _task("users/user", _user_payload()))

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
        assert (
            runner(_consumer(), _task("users/user", _user_payload())) == CallbackResult.SuccessCreated()
        )
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
    result = _runner(exc=TimeoutError())(_consumer(), _task("users/user", _user_payload()))

    assert result == CallbackResult.Failure("processing did not finish within 10s")


def test_runner_reports_other_errors_as_failure() -> None:
    result = _runner(exc=RuntimeError("db down"))(_consumer(), _task("users/user", _user_payload()))

    assert result == CallbackResult.Failure("RuntimeError: db down")


def test_runner_reports_an_unreadable_old_table_as_failure() -> None:
    task = _task("users/user", _user_payload())

    result = _runner()(_consumer(exc=OSError("ccf db down")), task)

    assert result == CallbackResult.Failure("OSError: ccf db down")


def test_runner_lets_a_ccf_database_error_escape() -> None:
    # The CCF retries a task without counting an error if its
    # `CcfDatabaseError` escapes the callback.
    task = _task("users/user", _user_payload())
    attrs = dict(task["attrs"])
    runner = _runner()
    consumer = _consumer(exc=CcfDatabaseError("ccf db down"))

    with pytest.raises(CcfDatabaseError, match="ccf db down"):
        runner(consumer, task)

    assert task["attrs"] == attrs
