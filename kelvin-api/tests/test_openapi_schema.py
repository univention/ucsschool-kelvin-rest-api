# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for the nullability of properties in the generated OpenAPI documents."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ucsschool.kelvin.constants import URL_API_V1_PREFIX, URL_API_V2_PREFIX
from ucsschool.kelvin.main import app
from ucsschool.kelvin.routers.v1.school_class import SchoolClassPatchDocument
from ucsschool.kelvin.routers.v1.user import NULL_REJECTING_USER_PATCH_FIELDS
from ucsschool.kelvin.routers.v1.workgroup import WorkGroupPatchDocument
from ucsschool.kelvin.service.dependency import check_db_compatibility

API_PREFIXES = [URL_API_V1_PREFIX, URL_API_V2_PREFIX]

MANDATORY_USER_PROPERTIES = ("dn", "url", "name", "firstname", "lastname", "roles", "schools")
OPTIONAL_USER_PROPERTIES_DEFAULTING_TO_SOMETHING_ELSE = (
    "disabled",
    "school_classes",
    "workgroups",
    "ucsschool_roles",
)

#: What the OpenAPI documents of both API versions must say about `nullable`.
DOCUMENTED_NULLABILITY: dict[str, dict[str, bool]] = {
    "UserModel": {
        # bug report: the API answers with '"birthday": null', the schema forbade it
        "birthday": True,
        "email": True,
        "expiration_date": True,
        "record_uid": True,
        "source_uid": True,
        **dict.fromkeys(MANDATORY_USER_PROPERTIES, False),
        **dict.fromkeys(OPTIONAL_USER_PROPERTIES_DEFAULTING_TO_SOMETHING_ELSE, False),
    },
    "UserPatchModel": {
        "birthday": True,
        "email": True,
        "expiration_date": True,
        # 'validate_null_values()' and 'only_known_udm_properties()' answer 422 for an
        # explicitly passed 'null'
        **dict.fromkeys(NULL_REJECTING_USER_PATCH_FIELDS + ("udm_properties",), False),
    },
    "SchoolModel": {
        "display_name": True,
        "class_share_file_server": True,
        "home_share_file_server": True,
    },
    # 'doc/docs/resource-classes.rst' and '-workgroups.rst' document 'null|string'
    "SchoolClassModel": {"description": True},
    "WorkGroupModel": {"description": True},
    # 'check_name()' answers 422 for an explicitly passed 'null', and a 'null' in
    # 'users' is deprecated and ignored rather than supported
    "SchoolClassPatchDocument": {"name": False, "users": False, "description": True},
    "WorkGroupPatchDocument": {"name": False, "users": False, "description": True},
}


@pytest.fixture(scope="module")
def openapi_docs() -> Iterator[dict[str, Any]]:
    """The generated OpenAPI document of each API version, keyed by URL prefix."""
    # The v2 router depends on the Kelvin DB being at the expected migration, which has
    # no bearing on the generated schema.
    app.dependency_overrides[check_db_compatibility] = lambda: True
    try:
        client = TestClient(app, base_url="http://test.server")
        docs: dict[str, Any] = {}
        for prefix in API_PREFIXES:
            response = client.get(f"{prefix}/openapi.json")
            assert response.status_code == 200, f"{prefix}: {response.text}"
            docs[prefix] = response.json()
        yield docs
    finally:
        _ = app.dependency_overrides.pop(check_db_compatibility, None)


def _schemas(doc: dict[str, Any]) -> dict[str, Any]:
    return doc["components"]["schemas"]


def _properties(doc: dict[str, Any], schema_name: str) -> dict[str, Any]:
    return _schemas(doc)[schema_name].get("properties", {})


def _is_nullable(prop: dict[str, Any]) -> bool:
    return {"type": "null"} in prop.get("anyOf", [])


def _nullable_properties(doc: dict[str, Any]) -> dict[str, set[str]]:
    """The names of the properties documented as nullable, per schema."""
    return {
        schema_name: {
            prop_name for prop_name, prop in schema.get("properties", {}).items() if _is_nullable(prop)
        }
        for schema_name, schema in _schemas(doc).items()
    }


@pytest.mark.parametrize("model", [SchoolClassPatchDocument, WorkGroupPatchDocument])
def test_a_deprecated_null_is_accepted_but_not_documented(model: type):
    """'users': null is ignored rather than supported, so it validates without being documented."""
    assert model.model_validate({"users": None}).users is None
    assert not _is_nullable(model.model_json_schema()["properties"]["users"])


@pytest.mark.parametrize("prefix", API_PREFIXES)
@pytest.mark.parametrize(
    "schema_name,prop_name,nullable",
    [
        (schema_name, prop_name, nullable)
        for schema_name, properties in DOCUMENTED_NULLABILITY.items()
        for prop_name, nullable in properties.items()
    ],
)
def test_documented_nullability(
    openapi_docs: dict[str, Any], prefix: str, schema_name: str, prop_name: str, nullable: bool
):
    prop = _properties(openapi_docs[prefix], schema_name)[prop_name]
    assert _is_nullable(prop) is nullable


@pytest.mark.parametrize("prefix", API_PREFIXES)
def test_mandatory_user_properties_stay_required(openapi_docs: dict[str, Any], prefix: str):
    required = _schemas(openapi_docs[prefix])["UserModel"]["required"]
    assert set(MANDATORY_USER_PROPERTIES) <= set(required)


def test_both_api_versions_agree_on_nullability(openapi_docs: dict[str, Any]):
    """v2 reuses v1's models, so the documented nullability must not diverge."""
    v1, v2 = (_nullable_properties(openapi_docs[prefix]) for prefix in API_PREFIXES)
    shared_schemas = v1.keys() & v2.keys()
    assert shared_schemas
    assert {name: v1[name] for name in shared_schemas} == {name: v2[name] for name in shared_schemas}
