import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kelvin_connector.consumer import KelvinConnectorEventHandler, KelvinConsumerModule
from kelvin_connector.models import UserProperties
from provisioning_consumer_lib import UDMEventHandler
from pydantic import ValidationError

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
        "id": "testuser",
        "position": "cn=users,dc=test",
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
        "name": "OUdemoschool-DC-Edukativnetz",
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


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def sync_manager():
    return AsyncMock()


@pytest.fixture
def handler(sync_manager):
    return KelvinConnectorEventHandler(sync_manager, MagicMock())


# ── is_relevant ───────────────────────────────────────────────────────────────


async def test_is_relevant_unknown_topic_returns_false(handler):
    event = {
        "topic": "unknown/type",
        "sequence_number": 1,
        "body": {"new": {"properties": {"ucsschoolRole": ["t"]}}},
    }
    assert await handler.is_relevant(event) is False


async def test_is_relevant_no_properties_returns_false(handler):
    event = {"topic": "users/user", "sequence_number": 1, "body": {"new": {}}}
    assert await handler.is_relevant(event) is False


async def test_is_relevant_no_ucsschool_role_returns_false(handler):
    event = {"topic": "users/user", "sequence_number": 1, "body": {"new": {"properties": {}}}}
    assert await handler.is_relevant(event) is False


async def test_is_relevant_reads_properties_from_old(handler):
    event = {
        "topic": "users/user",
        "sequence_number": 1,
        "body": {"old": {"properties": {"ucsschoolRole": ["teacher:school:DEMOSCHOOL"]}}},
    }
    assert await handler.is_relevant(event) is True


async def test_is_relevant_falls_back_to_new_when_old_has_no_properties(handler):
    event = {
        "topic": "users/user",
        "sequence_number": 1,
        "body": {
            "old": {},
            "new": {"properties": {"ucsschoolRole": ["teacher:school:DEMOSCHOOL"]}},
        },
    }
    assert await handler.is_relevant(event) is True


async def test_is_relevant_returns_true_for_user_topic(handler):
    event = {
        "topic": "users/user",
        "sequence_number": 1,
        "body": {"new": {"properties": {"ucsschoolRole": ["teacher:school:DEMOSCHOOL"]}}},
    }
    assert await handler.is_relevant(event) is True


async def test_is_relevant_skips_exam_user(handler):
    # Exam users are temporary copies and must not be cached.
    event = {
        "topic": "users/user",
        "sequence_number": 1,
        "body": {
            "new": {
                "properties": {
                    "ucsschoolRole": [
                        "exam_user:school:DEMOSCHOOL",
                        "exam_user:exam:demo-DEMOSCHOOL",
                    ]
                }
            }
        },
    }
    assert await handler.is_relevant(event) is False


async def test_is_relevant_returns_true_for_ou_topic(handler):
    event = {
        "topic": "container/ou",
        "sequence_number": 1,
        "body": {"new": {"properties": {"ucsschoolRole": ["school_admin:school:DEMOSCHOOL"]}}},
    }
    assert await handler.is_relevant(event) is True


async def test_is_relevant_group_with_school_class_role(handler):
    event = {
        "topic": "groups/group",
        "sequence_number": 1,
        "body": {"new": {"properties": {"ucsschoolRole": ["school_class:school:DEMOSCHOOL"]}}},
    }
    assert await handler.is_relevant(event) is True


async def test_is_relevant_group_with_workgroup_role(handler):
    event = {
        "topic": "groups/group",
        "sequence_number": 1,
        "body": {"new": {"properties": {"ucsschoolRole": ["workgroup:school:DEMOSCHOOL"]}}},
    }
    assert await handler.is_relevant(event) is True


async def test_is_relevant_group_with_unmatched_role_returns_false(handler):
    event = {
        "topic": "groups/group",
        "sequence_number": 1,
        "body": {"new": {"properties": {"ucsschoolRole": ["other_role:school:DEMOSCHOOL"]}}},
    }
    assert await handler.is_relevant(event) is False


# ── handle_event ──────────────────────────────────────────────────────────────


def _queue_event(num_delivered: int = 1, body: dict | None = None) -> dict:
    return {
        "publisher_name": "udm-listener",
        "ts": _TS,
        "realm": "udm",
        "topic": "users/user",
        "sequence_number": 42,
        "num_delivered": num_delivered,
        "body": body if body is not None else {"old": None, "new": _user_payload()},
    }


async def test_handle_event_delegates_to_super(handler):
    event = {"topic": "users/user", "body": {}}
    with patch.object(UDMEventHandler, "handle_event", new_callable=AsyncMock, return_value=True):
        assert await handler.handle_event(event) is True


async def test_handle_event_propagates_validation_error(handler):
    """Malformed events are no longer swallowed — what happens to a failed
    event is decided by KelvinConsumerModule."""
    payload = _user_payload()
    payload["properties"]["univentionObjectIdentifier"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        await handler.handle_event(_queue_event(body={"old": None, "new": payload}))


async def test_handle_event_propagates_handler_error_without_duplicate_logging(handler, sync_manager):
    sync_manager.handle_user_create.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError, match="boom"):
        await handler.handle_event(_queue_event())


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


async def test_handle_remove_user_with_malformed_state_still_dispatches(handler, sync_manager):
    """Deletion only needs the identifier: a user whose remaining LDAP state
    is malformed must still be removable from the cache — a dropped delete
    event leaves a stale row no future event can repair (e.g. one that holds
    a unique email forever)."""
    uid = _uid()
    payload = _user_payload(uid)
    payload["properties"]["firstname"] = None
    payload["properties"]["ucsschoolRole"] = ["123"]

    await handler._handle_remove(_meta(), payload)

    sync_manager.handle_user_delete.assert_called_once()
    event = sync_manager.handle_user_delete.call_args[0][0]
    assert str(event.old.properties.univentionObjectIdentifier) == uid
    assert event.old.properties.username == "testuser"


async def test_handle_remove_group_with_malformed_state_still_dispatches(handler, sync_manager):
    payload = _group_payload()
    payload["properties"]["ucsschoolRole"] = ["123"]

    await handler._handle_remove(_meta(), payload)

    sync_manager.handle_group_delete.assert_called_once()
    event = sync_manager.handle_group_delete.call_args[0][0]
    assert event.old.properties.name == "testgroup"


async def test_handle_remove_unknown_type_logs_error(handler, sync_manager):
    payload = {"objectType": "unknown/type", "dn": "cn=x,dc=test", "properties": {}}
    await handler._handle_remove(_meta(), payload)
    sync_manager.handle_user_event.assert_not_called()
    sync_manager.handle_group_event.assert_not_called()
    sync_manager.handle_school_event.assert_not_called()


# ── Host group events ─────────────────────────────────────────────────────────


async def test_is_relevant_group_with_host_group_name_returns_true(handler):
    event = {
        "topic": "groups/group",
        "sequence_number": 1,
        "body": {
            "old": {"properties": {"ucsschoolRole": []}},
            "new": {
                "properties": {
                    "ucsschoolRole": [],
                    "name": "OUdemoschool-DC-Edukativnetz",
                }
            },
        },
    }
    assert await handler.is_relevant(event) is True


async def test_is_relevant_both_old_and_new_have_ucsschool_role(handler):
    event = {
        "topic": "groups/group",
        "sequence_number": 1,
        "body": {
            "old": {"properties": {"ucsschoolRole": ["school_class:school:demoschool"]}},
            "new": {"properties": {"ucsschoolRole": ["school_class:school:demoschool"]}},
        },
    }
    assert await handler.is_relevant(event) is True


async def test_handle_create_host_group(handler, sync_manager):
    await handler._handle_create(_meta(), _host_group_payload())
    sync_manager.handle_host_group_create.assert_called_once()
    sync_manager.handle_group_create.assert_not_called()


async def test_handle_modify_host_group(handler, sync_manager):
    p = _host_group_payload()
    await handler._handle_modify(_meta(), p, p, has_moved=False)
    sync_manager.handle_host_group_modify.assert_called_once()
    sync_manager.handle_group_modify.assert_not_called()


async def test_handle_remove_host_group(handler, sync_manager):
    await handler._handle_remove(_meta(), _host_group_payload())
    sync_manager.handle_host_group_delete.assert_called_once()
    sync_manager.handle_group_delete.assert_not_called()


# ── KelvinConsumerModule delivery policy ──────────────────────────────────────


def _validation_error() -> ValidationError:
    try:
        UserProperties.parse_obj({"univentionObjectIdentifier": "not-a-uuid"})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


@pytest.fixture
def event_handler():
    h = AsyncMock()
    h.is_relevant.return_value = True
    h.handle_event.return_value = True
    return h


@pytest.fixture
def consumer(event_handler, tmp_path):
    consumer = KelvinConsumerModule(
        event_handler,
        session=MagicMock(),
        name="test-consumer",
        provisioning_url="https://provisioning.test",
        config_dir=str(tmp_path),
    )
    consumer._fetch_event = AsyncMock(return_value=_queue_event())
    consumer._acknowledge_event = AsyncMock()
    return consumer


async def test_consumer_acknowledges_successful_event(consumer):
    await consumer.process_one_event()
    consumer._acknowledge_event.assert_called_once()


async def test_consumer_acknowledges_irrelevant_event_without_handling(consumer, event_handler):
    event_handler.is_relevant.return_value = False
    await consumer.process_one_event()
    consumer._acknowledge_event.assert_called_once()
    event_handler.handle_event.assert_not_called()


async def test_consumer_does_nothing_on_long_polling_timeout(consumer, event_handler):
    consumer._fetch_event.return_value = None
    await consumer.process_one_event()
    event_handler.handle_event.assert_not_called()
    consumer._acknowledge_event.assert_not_called()


async def test_consumer_does_not_acknowledge_unhandled_event(consumer, event_handler):
    event_handler.handle_event.return_value = False
    await consumer.process_one_event()
    consumer._acknowledge_event.assert_not_called()


async def test_consumer_crashes_without_ack_while_deliveries_left(consumer, event_handler):
    """Transient failures get retried: the event is redelivered after restart."""
    event_handler.handle_event.side_effect = RuntimeError("boom")
    consumer._fetch_event.return_value = _queue_event(num_delivered=1)

    with pytest.raises(RuntimeError, match="boom"):
        await consumer.process_one_event()

    consumer._acknowledge_event.assert_not_called()


async def test_consumer_drops_event_after_delivery_budget_is_exhausted(consumer, event_handler):
    """A poison event is ejected: acknowledged so it is not redelivered, but
    the process still crashes to restart with a clean state."""
    event_handler.handle_event.side_effect = RuntimeError("boom")
    consumer._fetch_event.return_value = _queue_event(num_delivered=3)

    with pytest.raises(RuntimeError, match="boom"):
        await consumer.process_one_event()

    consumer._acknowledge_event.assert_called_once()


async def test_consumer_drops_malformed_event_without_crashing(consumer, event_handler):
    """Retrying cannot fix a malformed event and the handler never touched
    any state — acknowledge it and continue with the next event."""
    event_handler.handle_event.side_effect = _validation_error()
    consumer._fetch_event.return_value = _queue_event(num_delivered=1)

    await consumer.process_one_event()

    consumer._acknowledge_event.assert_called_once()
