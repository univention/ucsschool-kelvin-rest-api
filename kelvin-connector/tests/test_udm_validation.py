import pytest
from kelvin_connector.models import EmptyDict, UDMEventObject, UDMPayload
from pydantic import ValidationError

VALID_BODY = {"dn": "cn=foo", "objectType": "user", "id": "123"}
VALID_WITH_EXTRA = {**VALID_BODY, "extra_field": "kept"}

EVENT = {
    "publisher_name": "udm-listener",
    "ts": "2025-01-01T00:00:00Z",
    "realm": "udm",
    "topic": "users",
    "sequence_number": 1,
    "num_delivered": 0,
}


def event(body):
    return {**EVENT, "body": body}


VALID_BODY_CASES = [
    pytest.param({"old": {}, "new": VALID_BODY}, (EmptyDict, UDMPayload), id="old-empty-new-payload"),
    pytest.param({"old": VALID_BODY, "new": {}}, (UDMPayload, EmptyDict), id="old-payload-new-empty"),
    pytest.param({"old": VALID_BODY, "new": VALID_BODY}, (UDMPayload, UDMPayload), id="both-payload"),
    pytest.param(
        {"old": VALID_WITH_EXTRA, "new": {}}, (UDMPayload, EmptyDict), id="payload-with-extra-allowed"
    ),
]

INVALID_BODY_CASES = [
    pytest.param({"old": {}, "new": {}}, id="both-empty-rejected"),
    pytest.param({"old": {"dn": "x"}, "new": {}}, id="old-missing-fields"),
    pytest.param({"old": {}, "new": {"dn": "x", "objectType": "y"}}, id="new-missing-id"),
    pytest.param({"old": {**VALID_BODY, "dn": ""}, "new": {}}, id="empty-string-dn"),
    pytest.param({"old": {**VALID_BODY, "objectType": ""}, "new": {}}, id="empty-string-objectType"),
    pytest.param({"old": {**VALID_BODY, "id": ""}, "new": {}}, id="empty-string-id"),
    pytest.param({"old": "not a dict", "new": {}}, id="old-not-a-dict"),
    pytest.param({"old": {}, "new": None}, id="new-is-none"),
    pytest.param({"new": {}}, id="missing-old"),
    pytest.param({"old": {}}, id="missing-new"),
]

INVALID_WRAPPER_CASES = [
    pytest.param({k: v for k, v in EVENT.items() if k != "publisher_name"}, id="missing-publisher_name"),
    pytest.param({**EVENT, "sequence_number": "not-an-int"}, id="sequence_number-wrong-type"),
    pytest.param({**EVENT, "num_delivered": None}, id="num_delivered-none"),
]


@pytest.mark.parametrize("body,expected_types", VALID_BODY_CASES)
def test_valid_event(body, expected_types):
    obj = UDMEventObject.validate(event(body))
    assert isinstance(obj.body.old, expected_types[0])
    assert isinstance(obj.body.new, expected_types[1])

    assert obj.publisher_name == EVENT["publisher_name"]
    assert obj.sequence_number == EVENT["sequence_number"]


@pytest.mark.parametrize("body", INVALID_BODY_CASES)
def test_invalid_body_in_event(body):
    with pytest.raises(ValidationError) as exc_info:
        UDMEventObject.validate(event(body))
    locs = [e["loc"] for e in exc_info.value.errors()]
    assert any("body" in loc for loc in locs)


@pytest.mark.parametrize("event_wrapper", INVALID_WRAPPER_CASES)
def test_invalid_wrapper(event_wrapper):
    payload = {**event_wrapper, "body": {"old": {}, "new": VALID_BODY}}
    with pytest.raises(ValidationError):
        UDMEventObject.validate(payload)
