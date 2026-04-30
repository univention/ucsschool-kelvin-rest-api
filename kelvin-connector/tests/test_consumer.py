import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kelvin_connector.consumer import KelvinConnectorEventHandler
from kelvin_connector.models import UserProperties
from provisioning_consumer_lib import UDMEventHandler

_TS = "2024-01-01T00:00:00"


def _uid() -> str:
    return str(uuid.uuid4())


def _meta() -> dict:
    return {
        "publisher_name": "test",
        "ts": _TS,
        "realm": "udm",
        "topic": "users/user",
        "sequence_number": 1,
        "num_delivered": 1,
    }


def _user_payload(uid: str | None = None) -> dict:
    return {
        "objectType": "users/user",
        "dn": "uid=testuser,cn=users,dc=test",
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


def _school_payload(uid: str | None = None) -> dict:
    return {
        "objectType": "container/ou",
        "dn": "ou=testschool,dc=test",
        "properties": {
            "univentionObjectIdentifier": uid or _uid(),
            "name": "testschool",
            "displayName": "testschool Display",
        },
    }


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def sync_manager():
    return AsyncMock()


@pytest.fixture
def handler(sync_manager):
    return KelvinConnectorEventHandler(sync_manager, MagicMock())


# ── is_relevant ───────────────────────────────────────────────────────────────


async def test_is_relevant_unknown_topic_returns_false(handler):
    event = {"topic": "unknown/type", "body": {"new": {"properties": {"ucsschoolRole": ["t"]}}}}
    assert await handler.is_relevant(event) is False


async def test_is_relevant_no_properties_returns_false(handler):
    event = {"topic": "users/user", "body": {"new": {}}}
    assert await handler.is_relevant(event) is False


async def test_is_relevant_no_ucsschool_role_returns_false(handler):
    event = {"topic": "users/user", "body": {"new": {"properties": {}}}}
    assert await handler.is_relevant(event) is False


async def test_is_relevant_reads_properties_from_old(handler):
    event = {
        "topic": "users/user",
        "body": {"old": {"properties": {"ucsschoolRole": ["teacher:school:DEMOSCHOOL"]}}},
    }
    assert await handler.is_relevant(event) is True


async def test_is_relevant_falls_back_to_new_when_old_has_no_properties(handler):
    event = {
        "topic": "users/user",
        "body": {
            "old": {},
            "new": {"properties": {"ucsschoolRole": ["teacher:school:DEMOSCHOOL"]}},
        },
    }
    assert await handler.is_relevant(event) is True


async def test_is_relevant_returns_true_for_user_topic(handler):
    event = {
        "topic": "users/user",
        "body": {"new": {"properties": {"ucsschoolRole": ["teacher:school:DEMOSCHOOL"]}}},
    }
    assert await handler.is_relevant(event) is True


async def test_is_relevant_returns_true_for_ou_topic(handler):
    event = {
        "topic": "container/ou",
        "body": {"new": {"properties": {"ucsschoolRole": ["school_admin:school:DEMOSCHOOL"]}}},
    }
    assert await handler.is_relevant(event) is True


async def test_is_relevant_group_with_school_class_role(handler):
    event = {
        "topic": "groups/group",
        "body": {"new": {"properties": {"ucsschoolRole": ["school_class:school:DEMOSCHOOL"]}}},
    }
    assert await handler.is_relevant(event) is True


async def test_is_relevant_group_with_workgroup_role(handler):
    event = {
        "topic": "groups/group",
        "body": {"new": {"properties": {"ucsschoolRole": ["workgroup:school:DEMOSCHOOL"]}}},
    }
    assert await handler.is_relevant(event) is True


async def test_is_relevant_group_with_unmatched_role_returns_false(handler):
    event = {
        "topic": "groups/group",
        "body": {"new": {"properties": {"ucsschoolRole": ["other_role:school:DEMOSCHOOL"]}}},
    }
    assert await handler.is_relevant(event) is False


# ── handle_event ──────────────────────────────────────────────────────────────


async def test_handle_event_delegates_to_super(handler):
    event = {"topic": "users/user", "body": {}}
    with patch.object(UDMEventHandler, "handle_event", new_callable=AsyncMock, return_value=True):
        assert await handler.handle_event(event) is True


async def test_handle_event_catches_validation_error_and_returns_true(handler):
    from pydantic import ValidationError

    async def _raise(*_args, **_kwargs):
        try:
            UserProperties.parse_obj({"univentionObjectIdentifier": "not-a-uuid"})
        except ValidationError as exc:
            raise exc

    with patch.object(UDMEventHandler, "handle_event", new=_raise):
        assert await handler.handle_event({"body": {}}) is True


# ── _handle_create ────────────────────────────────────────────────────────────


async def test_handle_create_user(handler, sync_manager):
    await handler._handle_create(_meta(), _user_payload())
    sync_manager.handle_user_create.assert_called_once()


async def test_handle_create_group(handler, sync_manager):
    await handler._handle_create(_meta(), _group_payload())
    sync_manager.handle_group_create.assert_called_once()


async def test_handle_create_school(handler, sync_manager):
    await handler._handle_create(_meta(), _school_payload())
    sync_manager.handle_school_create.assert_called_once()


async def test_handle_create_unknown_type_logs_error(handler, sync_manager):
    payload = {"objectType": "unknown/type", "dn": "cn=x,dc=test", "properties": {}}
    await handler._handle_create(_meta(), payload)
    sync_manager.handle_user_event.assert_not_called()
    sync_manager.handle_group_event.assert_not_called()
    sync_manager.handle_school_event.assert_not_called()


# ── _handle_modify ────────────────────────────────────────────────────────────


async def test_handle_modify_user(handler, sync_manager):
    p = _user_payload()
    await handler._handle_modify(_meta(), p, p, has_moved=False)
    sync_manager.handle_user_modify.assert_called_once()


async def test_handle_modify_group(handler, sync_manager):
    p = _group_payload()
    await handler._handle_modify(_meta(), p, p, has_moved=False)
    sync_manager.handle_group_modify.assert_called_once()


async def test_handle_modify_school(handler, sync_manager):
    p = _school_payload()
    await handler._handle_modify(_meta(), p, p, has_moved=False)
    sync_manager.handle_school_modify.assert_called_once()


async def test_handle_modify_unknown_type_logs_error(handler, sync_manager):
    payload = {"objectType": "unknown/type", "dn": "cn=x,dc=test", "properties": {}}
    await handler._handle_modify(_meta(), payload, payload, has_moved=False)
    sync_manager.handle_user_event.assert_not_called()
    sync_manager.handle_group_event.assert_not_called()
    sync_manager.handle_school_event.assert_not_called()


# ── _handle_remove ────────────────────────────────────────────────────────────


async def test_handle_remove_user(handler, sync_manager):
    await handler._handle_remove(_meta(), _user_payload())
    sync_manager.handle_user_delete.assert_called_once()


async def test_handle_remove_group(handler, sync_manager):
    await handler._handle_remove(_meta(), _group_payload())
    sync_manager.handle_group_delete.assert_called_once()


async def test_handle_remove_school(handler, sync_manager):
    await handler._handle_remove(_meta(), _school_payload())
    sync_manager.handle_school_delete.assert_called_once()


async def test_handle_remove_unknown_type_logs_error(handler, sync_manager):
    payload = {"objectType": "unknown/type", "dn": "cn=x,dc=test", "properties": {}}
    await handler._handle_remove(_meta(), payload)
    sync_manager.handle_user_event.assert_not_called()
    sync_manager.handle_group_event.assert_not_called()
    sync_manager.handle_school_event.assert_not_called()
