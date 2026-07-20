from typing import TypedDict

import pytest
from ucsschool_objects.core.domain.errors import PatchShapeMismatch
from ucsschool_objects.core.domain.patch_types import (
    GroupPatchDict,
    MembershipPatchDict,
    SchoolPatchDict,
    as_patch_dict,
)

_SCHOOL_PATCH: dict[str, object] = {
    "record_uid": "rec",
    "source_uid": "src",
    "name": "school",
    "display_name": "School",
    "educational_servers": ["edu1"],
    "administrative_servers": ["adm1"],
    "class_share_file_server": None,
    "home_share_file_server": None,
    "udm_properties": {},
}


class _RequiredKeysDict(TypedDict):
    name: str
    display_name: str


def test_as_patch_dict_accepts_exact_required_keys() -> None:
    result = as_patch_dict(_SCHOOL_PATCH, SchoolPatchDict)
    assert result == _SCHOOL_PATCH


def test_as_patch_dict_accepts_public_id_field() -> None:
    data: dict[str, object] = {**_SCHOOL_PATCH, "public_id": "some-uuid"}
    result = as_patch_dict(data, SchoolPatchDict)
    assert result is data
    assert data.get("public_id", None) == "some-uuid"


def test_as_patch_dict_accepts_missing_keys_for_total_false_typed_dict() -> None:
    data = dict(_SCHOOL_PATCH)
    del data["name"]
    del data["display_name"]
    result = as_patch_dict(data, SchoolPatchDict)
    assert result == data


def test_as_patch_dict_accepts_empty_dict_for_group() -> None:
    result = as_patch_dict({}, GroupPatchDict)
    assert result == {}


def test_as_patch_dict_accepts_empty_dict_for_membership() -> None:
    result = as_patch_dict({}, MembershipPatchDict)
    assert result == {}


def test_as_patch_dict_raises_on_missing_required_key() -> None:
    with pytest.raises(PatchShapeMismatch) as excinfo:
        _ = as_patch_dict({}, _RequiredKeysDict)
    assert excinfo.value.patch_type == "_RequiredKeysDict"
    assert excinfo.value.missing_keys == frozenset({"name", "display_name"})
    assert excinfo.value.undefined_keys == frozenset()
    assert "name" in str(excinfo.value)
    assert "display_name" in str(excinfo.value)


def test_as_patch_dict_raises_on_undefined_key() -> None:
    data: dict[str, object] = {**_SCHOOL_PATCH, "not_a_field": "oops"}
    with pytest.raises(PatchShapeMismatch) as excinfo:
        _ = as_patch_dict(data, SchoolPatchDict)
    assert excinfo.value.patch_type == "SchoolPatchDict"
    assert excinfo.value.missing_keys == frozenset()
    assert excinfo.value.undefined_keys == frozenset({"not_a_field"})
    assert "not_a_field" in str(excinfo.value)
