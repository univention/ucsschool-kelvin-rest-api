from __future__ import annotations

import uuid
from datetime import date

from tests.core.domain.helpers.model_builders import school as build_school
from ucsschool_objects.core.domain.json import normalise, to_json
from ucsschool_objects.core.domain.models import UNLOADED, UNSET


def testnormalise_sorts_flat_list() -> None:
    assert normalise(["c", "a", "b"]) == ["a", "b", "c"]


def testnormalise_empty_list() -> None:
    assert normalise([]) == []


def testnormalise_leaves_scalar_unchanged() -> None:
    assert normalise("hello") == "hello"
    assert normalise(42) == 42
    assert normalise(None) is None


def testnormalise_sorts_nested_list_in_dict() -> None:
    result = normalise({"servers": ["z", "a", "m"]})
    assert result == {"servers": ["a", "m", "z"]}


def testnormalise_sorts_list_of_dicts_by_str() -> None:
    items = [{"name": "z"}, {"name": "a"}]
    result = normalise(items)
    assert result == sorted(items, key=str)


def testnormalise_converts_set_to_sorted_list() -> None:
    result = normalise({"c", "a", "b"})
    assert result == ["a", "b", "c"]


def testnormalise_converts_frozenset_to_sorted_list() -> None:
    result = normalise(frozenset({"c", "a", "b"}))
    assert result == ["a", "b", "c"]


def testnormalise_converts_uuid_to_str() -> None:
    value = uuid.uuid4()
    assert normalise(value) == str(value)


def testnormalise_converts_uuid_dict_key_to_str() -> None:
    value = uuid.uuid4()
    result = normalise({value: "payload"})
    assert result == {str(value): "payload"}


def testnormalise_converts_date_to_isoformat() -> None:
    value = date(2024, 1, 15)
    assert normalise(value) == "2024-01-15"


def testnormalise_recurses_into_nested_dicts() -> None:
    result = normalise({"outer": {"inner": ["b", "a"]}})
    assert result == {"outer": {"inner": ["a", "b"]}}


def testnormalise_converts_unloaded_to_marker() -> None:
    assert normalise(UNLOADED) == {"__sentinel__": "UNLOADED"}


def testnormalise_converts_unset_to_marker() -> None:
    assert normalise(UNSET) == {"__sentinel__": "UNSET"}


def test_to_json_normalises_domain_object() -> None:
    school = build_school()
    result = to_json(school)
    assert result["public_id"] == str(school.public_id)
    assert result["educational_servers"] == ["srv"]
    assert result["display_name"] == {"__sentinel__": "UNLOADED"}
