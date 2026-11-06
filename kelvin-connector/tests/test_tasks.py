# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
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
    Outcome,
    OutcomeKind,
    TaskProcessor,
    TaskRunner,
    is_relevant,
    to_callback_result,
)

_TS = "2024-01-01T00:00:00"


def _uid() -> str:
    return str(uuid.uuid4())


def _user_payload(uid: str | None = None) -> dict:
    return {
        "objectType": "users/user",
        "dn": "uid=testuser,cn=users,ou=TestSchool,dc=test",
        "id": "testuser",
        "position": "cn=users,ou=TestSchool,dc=test",
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


def _group_payload(uid: str | None = None) -> dict:
    return {
        "objectType": "groups/group",
        "dn": "cn=testgroup,cn=klassen,dc=test",
        "id": "testgroup",
        "position": "cn=klassen,dc=test",
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


def _host_group_payload(uid: str | None = None) -> dict:
    return {
        "objectType": "groups/group",
        "dn": "cn=OUdemoschool-DC-Edukativnetz,cn=ucsschool,cn=groups,dc=test",
        "id": "OUdemoschool-DC-Edukativnetz",
        "position": "cn=ucsschool,cn=groups,dc=test",
        "properties": {
            "univentionObjectIdentifier": uid or _uid(),
            "name": "OUdemoschool-DC-Edukativnetz",
            "description": "DC host group for demoschool",
            "hosts": [],
        },
    }


def _school_payload(uid: str | None = None) -> dict:
    return {
        "objectType": "container/ou",
        "dn": "ou=testschool,dc=test",
        "position": "dc=test",
        "id": "testschool",
        "properties": {
            "univentionObjectIdentifier": uid or _uid(),
            "name": "testschool",
            "displayName": "testschool Display",
        },
    }


def _task(udm_module: str, old: dict | None = None, new: dict | None = None) -> dict:
    """A task dict as the CCF hands it to the Python callback."""
    old = old or {}
    new = new or {}
    return {
        "id": 1,
        "obj_id": (new or old).get("id", "obj"),
        "udm_module": udm_module,
        "dn": (new or old).get("dn", "").lower(),
        "attrs": new.get("properties", {}),
        "status": "new",
        "num_errors": 0,
        "request_id": "req-1",
        "delay": 0,
        "seq_number": 42,
        "ts": _TS,
        "old": old,
        "new": new,
    }


def _roles_task(udm_module: str, *roles: str, side: str = "new", name: str = "") -> dict:
    payload = {"properties": {"ucsschoolRole": list(roles), "name": name}}
    return _task(udm_module, **{side: payload})


# ── is_relevant ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "task",
    [
        pytest.param(_roles_task("users/user", "teacher:school:DEMOSCHOOL"), id="user"),
        pytest.param(_roles_task("users/user", "teacher:school:DEMOSCHOOL", side="old"), id="delete"),
        pytest.param(_roles_task("container/ou", "school_admin:school:DEMOSCHOOL"), id="ou"),
        pytest.param(_roles_task("groups/group", "school_class:school:DEMOSCHOOL"), id="school_class"),
        pytest.param(_roles_task("groups/group", "workgroup:school:DEMOSCHOOL"), id="workgroup"),
        pytest.param(
            _roles_task("groups/group", "other:school:DEMOSCHOOL", name="OUdemo-DC-Verwaltungsnetz"),
            id="host_group",
        ),
    ],
)
def test_is_relevant_accepts_school_objects(task):
    assert is_relevant(task) is True


@pytest.mark.parametrize(
    "task",
    [
        pytest.param(_roles_task("unknown/type", "t"), id="unknown_type"),
        pytest.param(_task("users/user"), id="no_properties"),
        pytest.param(_task("users/user", new={"properties": {}}), id="no_ucsschool_role"),
        pytest.param(
            _roles_task("users/user", "exam_user:school:DEMOSCHOOL", "exam_user:exam:demo-DEMOSCHOOL"),
            id="exam_user",
        ),
        pytest.param(_roles_task("groups/group", "other_role:school:DEMOSCHOOL"), id="other_group"),
    ],
)
def test_is_relevant_skips_other_objects(task):
    assert is_relevant(task) is False


def test_is_relevant_uses_the_new_roles_when_both_sides_have_roles():
    task = _task(
        "groups/group",
        old={"properties": {"ucsschoolRole": ["workgroup:school:DEMOSCHOOL"]}},
        new={"properties": {"ucsschoolRole": ["other_role:school:DEMOSCHOOL"]}},
    )
    assert is_relevant(task) is False


# ── TaskProcessor ─────────────────────────────────────────────────────────────


@pytest.fixture
def sync_manager():
    return AsyncMock()


@pytest.fixture
def processor(sync_manager):
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
async def test_process_create(processor, sync_manager, udm_module, payload, handler, event_cls):
    new = payload()

    outcome = await processor.process(_task(udm_module, new=new))

    assert outcome == Outcome(OutcomeKind.CREATED)
    (event,), _ = getattr(sync_manager, handler).call_args
    assert isinstance(event, event_cls)
    assert event.sequence_number == 42
    assert event.timestamp == _TS
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
async def test_process_modify(processor, sync_manager, udm_module, payload, handler, event_cls):
    uid = _uid()

    outcome = await processor.process(_task(udm_module, old=payload(uid), new=payload(uid)))

    assert outcome == Outcome(OutcomeKind.MODIFIED)
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
async def test_process_delete(processor, sync_manager, udm_module, payload, handler, event_cls):
    uid = _uid()

    outcome = await processor.process(_task(udm_module, old=payload(uid)))

    assert outcome == Outcome(OutcomeKind.DELETED)
    (event,), _ = getattr(sync_manager, handler).call_args
    assert isinstance(event, event_cls)
    assert str(event.old.properties.univentionObjectIdentifier) == uid


async def test_process_delete_with_malformed_state_still_dispatches(processor, sync_manager):
    uid = _uid()
    old = _user_payload(uid)
    old["properties"] = {"univentionObjectIdentifier": uid, "ucsschoolRole": ["garbage"]}

    outcome = await processor.process(_task("users/user", old=old))

    assert outcome == Outcome(OutcomeKind.DELETED)
    sync_manager.handle_user_delete.assert_awaited_once()


@pytest.mark.parametrize(
    "side",
    [
        {"new": {"properties": {}}},
        {"old": {"properties": {}}, "new": {"properties": {}}},
        {"old": {"p": 1}},
    ],
    ids=["create", "modify", "delete"],
)
async def test_process_skips_unknown_object_types(processor, sync_manager, side):
    outcome = await processor.process(_task("unknown/type", **side))

    assert outcome == Outcome(OutcomeKind.SKIPPED)
    assert sync_manager.mock_calls == []


async def test_process_reports_invalid_data_as_permanent_failure_without_values(processor, sync_manager):
    new = _user_payload()
    new["properties"]["birthday"] = "secret-not-a-date"

    outcome = await processor.process(_task("users/user", new=new))

    assert outcome.kind is OutcomeKind.PERMANENT_FAILURE
    assert "properties.birthday" in outcome.msg
    assert "secret-not-a-date" not in outcome.msg
    sync_manager.handle_user_create.assert_not_awaited()


async def test_process_propagates_handler_errors(processor, sync_manager):
    sync_manager.handle_user_create.side_effect = RuntimeError("db down")

    with pytest.raises(RuntimeError, match="db down"):
        await processor.process(_task("users/user", new=_user_payload()))


# ── TaskRunner ────────────────────────────────────────────────────────────────


class _InlineLoopThread:
    """Runs the coroutine right away instead of on a separate loop thread."""

    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc
        self.timeouts: list[float | None] = []

    def run(self, coro, timeout=None):
        self.timeouts.append(timeout)
        if self.exc:
            coro.close()
            raise self.exc
        return asyncio.run(coro)


def test_runner_skips_irrelevant_tasks_without_using_the_loop():
    loop_thread = MagicMock()
    runner = TaskRunner(loop_thread, MagicMock(), timeout=10)

    assert runner(_roles_task("groups/group", "other_role:school:X")) == Outcome(OutcomeKind.SKIPPED)
    loop_thread.run.assert_not_called()


def test_runner_processes_relevant_tasks_on_the_loop_with_the_timeout():
    loop_thread = _InlineLoopThread()
    runner = TaskRunner(loop_thread, TaskProcessor(AsyncMock()), timeout=10)

    assert runner(_task("users/user", new=_user_payload())) == Outcome(OutcomeKind.CREATED)
    assert loop_thread.timeouts == [10]


def test_runner_reports_a_timeout_as_failure():
    runner = TaskRunner(_InlineLoopThread(TimeoutError()), TaskProcessor(AsyncMock()), timeout=10)

    outcome = runner(_task("users/user", new=_user_payload()))

    assert outcome == Outcome(OutcomeKind.FAILURE, "processing did not finish within 10s")


def test_runner_reports_other_errors_as_failure():
    runner = TaskRunner(
        _InlineLoopThread(RuntimeError("db down")), TaskProcessor(AsyncMock()), timeout=10
    )

    outcome = runner(_task("users/user", new=_user_payload()))

    assert outcome == Outcome(OutcomeKind.FAILURE, "RuntimeError: db down")


# ── to_callback_result ────────────────────────────────────────────────────────


class _FakeCallbackResult:
    SuccessDeleted = "SuccessDeleted"
    SuccessSkipped = "SuccessSkipped"

    @staticmethod
    def SuccessCreated():
        return "SuccessCreated"

    @staticmethod
    def SuccessModified():
        return "SuccessModified"

    @staticmethod
    def Failure(msg):
        return ("Failure", msg)

    @staticmethod
    def PermanentFailure(msg):
        return ("PermanentFailure", msg)


@pytest.mark.parametrize(
    "outcome, expected",
    [
        (Outcome(OutcomeKind.CREATED), "SuccessCreated"),
        (Outcome(OutcomeKind.MODIFIED), "SuccessModified"),
        (Outcome(OutcomeKind.DELETED), "SuccessDeleted"),
        (Outcome(OutcomeKind.SKIPPED), "SuccessSkipped"),
        (Outcome(OutcomeKind.FAILURE, "boom"), ("Failure", "boom")),
        (Outcome(OutcomeKind.PERMANENT_FAILURE, "invalid"), ("PermanentFailure", "invalid")),
    ],
)
def test_to_callback_result_maps_every_outcome(outcome, expected):
    assert to_callback_result(_FakeCallbackResult, outcome) == expected
