# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
Tests for the nullability of properties in the generated OpenAPI documents.

pydantic 1.x omits `nullable` from the schema of fields that accept `None`, which made
the documents contradict the responses: a user without a birthday is serialized as
`"birthday": null`, while the schema declared `birthday` to be a date string.
`ucsschool.kelvin.schema.KelvinBaseModel` adds the missing `nullable`.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.openapi.utils import get_flat_models_from_routes
from fastapi.testclient import TestClient
from pydantic import BaseModel
from pydantic.schema import get_model_name_map

from ucsschool.kelvin.constants import URL_API_V1_PREFIX, URL_API_V2_PREFIX
from ucsschool.kelvin.main import app
from ucsschool.kelvin.routers.v1.doc import _routes_for_prefix
from ucsschool.kelvin.routers.v1.user import NULL_REJECTING_USER_PATCH_FIELDS
from ucsschool.kelvin.schema import KelvinBaseModel, mark_nullable_properties
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


def _nullable_properties(doc: dict[str, Any]) -> dict[str, set[str]]:
    """The names of the properties documented as nullable, per schema."""
    return {
        schema_name: {
            prop_name for prop_name, prop in schema.get("properties", {}).items() if prop.get("nullable")
        }
        for schema_name, schema in _schemas(doc).items()
    }


class ModelWithEveryKindOfField(KelvinBaseModel):
    mandatory: str
    # the implicit spelling of an optional field used throughout the routers …
    optional: str = None  # pyright: ignore[reportAssignmentType]
    # … and the explicit one
    optional_explicitly: int | None = None
    flag: bool = False
    items: list[str] = []
    mapping: dict[str, str] = {}
    rejects_null: str | None = None

    class Config(KelvinBaseModel.Config):
        non_nullable_fields: tuple[str, ...] = ("rejects_null",)


@pytest.mark.parametrize(
    "field_name,nullable",
    [
        ("mandatory", False),
        ("optional", True),
        ("optional_explicitly", True),
        ("flag", False),
        ("items", False),
        ("mapping", False),
        ("rejects_null", False),
    ],
)
def test_only_fields_accepting_none_are_marked_nullable(field_name: str, nullable: bool):
    prop = ModelWithEveryKindOfField.schema()["properties"][field_name]
    assert prop.get("nullable", False) is nullable


def test_a_nullable_reference_is_wrapped_before_being_marked():
    """OpenAPI 3.0 ignores every keyword next to a `$ref`, `nullable` included."""

    class Nested(KelvinBaseModel):
        value: str = ""

    class Model(KelvinBaseModel):
        nested: Nested | None = None

    prop = Model.schema()["properties"]["nested"]
    assert prop == {"allOf": [{"$ref": "#/definitions/Nested"}], "nullable": True}


def test_a_field_without_a_property_is_skipped():
    class Model(BaseModel):
        optional: str | None = None

    schema: dict[str, Any] = {"properties": {}}
    mark_nullable_properties(schema, Model)
    assert schema == {"properties": {}}


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
    assert prop.get("nullable", False) is nullable


@pytest.mark.parametrize("prefix", API_PREFIXES)
def test_mandatory_user_properties_stay_required(openapi_docs: dict[str, Any], prefix: str):
    required = _schemas(openapi_docs[prefix])["UserModel"]["required"]
    assert set(MANDATORY_USER_PROPERTIES) <= set(required)


@pytest.mark.parametrize("prefix", API_PREFIXES)
def test_nullable_is_never_a_sibling_of_a_ref(openapi_docs: dict[str, Any], prefix: str):
    siblings_of_a_ref = [
        f"{schema_name}.{prop_name}"
        for schema_name, schema in _schemas(openapi_docs[prefix]).items()
        for prop_name, prop in schema.get("properties", {}).items()
        if "nullable" in prop and "$ref" in prop
    ]
    assert siblings_of_a_ref == []


@pytest.mark.parametrize("prefix", API_PREFIXES)
def test_every_documented_model_marks_its_nullable_properties(prefix: str):
    """`KelvinBaseModel.Config.schema_extra` is the only thing that adds `nullable`, and a
    model that does not run it is indistinguishable from one without nullable fields."""
    documented_models = [
        model
        for model in get_flat_models_from_routes(_routes_for_prefix(app, prefix))
        if issubclass(model, BaseModel)
    ]
    assert documented_models
    assert [
        model.__name__
        for model in documented_models
        if model.__config__.schema_extra is not KelvinBaseModel.Config.schema_extra
    ] == []


@pytest.mark.parametrize("prefix", API_PREFIXES)
def test_the_documents_agree_with_every_models_fields(openapi_docs: dict[str, Any], prefix: str):
    """`DOCUMENTED_NULLABILITY` states the expectations of the bug report by hand. This
    covers the remaining models, so that a model added later cannot document the wrong
    nullability without being noticed."""
    schemas = _schemas(openapi_docs[prefix])
    mismatches: list[str] = []
    checked = 0
    for model, schema_name in get_model_name_map(
        get_flat_models_from_routes(_routes_for_prefix(app, prefix))
    ).items():
        schema = schemas.get(schema_name)
        # 'get_model_name_map()' also returns the enums of the document
        if schema is None or not issubclass(model, BaseModel):
            continue
        properties = schema.get("properties", {})
        non_nullable: tuple[str, ...] = getattr(model.__config__, "non_nullable_fields", ())
        for field in model.__fields__.values():
            prop = properties.get(field.alias)
            if prop is None:
                continue
            expected = field.allow_none and field.name not in non_nullable
            if prop.get("nullable", False) is not expected:
                mismatches.append(f"{schema_name}.{field.alias}: expected nullable={expected}")
            checked += 1
    assert checked, "no property checked"
    assert mismatches == []


def test_both_api_versions_agree_on_nullability(openapi_docs: dict[str, Any]):
    """v2 reuses v1's models, so the documented nullability must not diverge."""
    v1, v2 = (_nullable_properties(openapi_docs[prefix]) for prefix in API_PREFIXES)
    shared_schemas = v1.keys() & v2.keys()
    assert shared_schemas
    assert {name: v1[name] for name in shared_schemas} == {name: v2[name] for name in shared_schemas}
