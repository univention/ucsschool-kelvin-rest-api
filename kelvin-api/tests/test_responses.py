# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
# pyright: reportMissingTypeStubs=false

"""``model_list_response`` must put out what FastAPI's encoder would have.

The v2 collection endpoints return an already-serialised response, so
``serialize_response`` never runs on them and nothing else compares the two
payloads outside the in-container parity tests.

Each collection's actual response model is filled with every field it has, so
a field type orjson serialises differently from ``jsonable_encoder`` fails
here as soon as it is added to one of them.
"""

import datetime
from collections.abc import Callable

import orjson
import pytest
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

import ucsschool.kelvin.routers.v1.base
from ucsschool.kelvin.config import UDMMappingConfiguration
from ucsschool.kelvin.routers.v1.role import RoleModel
from ucsschool.kelvin.routers.v1.school import SchoolModel
from ucsschool.kelvin.routers.v1.school_class import SchoolClassModel
from ucsschool.kelvin.routers.v1.user import UserModel
from ucsschool.kelvin.routers.v1.workgroup import WorkGroupModel
from ucsschool.kelvin.routers.v2._responses import model_list_response

BASE = "https://kelvin.example.com/ucsschool/kelvin/v2"
SCHOOL = "DEMOSCHOOL"
LDAP_BASE = "dc=example,dc=com"

#: A nested value with the JSON types a jsonb ``udm_properties`` column can hold.
UDM_PROPERTIES = {"uidNumber": 2000, "title": None, "groups": [{"cn": "x", "active": True}]}


@pytest.fixture(autouse=True)
def udm_mapping_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow ``UDM_PROPERTIES`` without reading the import configuration."""
    names = list(UDM_PROPERTIES)
    config = UDMMappingConfiguration.construct(
        school=names, user=names, school_class=names, workgroup=names
    )
    monkeypatch.setattr(ucsschool.kelvin.routers.v1.base, "UDM_MAPPING_CONFIG", config)


def _user() -> UserModel:
    return UserModel.parse_obj(
        {
            "name": "alice",
            "firstname": "Alice",
            "lastname": "Doe",
            "school": f"{BASE}/schools/{SCHOOL}",
            "schools": [f"{BASE}/schools/{SCHOOL}"],
            "roles": [f"{BASE}/roles/student"],
            "birthday": datetime.date(2005, 3, 1),
            "expiration_date": datetime.date(2030, 7, 31),
            "record_uid": "alice",
            "school_classes": {SCHOOL: ["1a", "2b"]},
            "workgroups": {SCHOOL: ["chess"]},
            "ucsschool_roles": [f"student:school:{SCHOOL}"],
            "legal_guardians": [f"{BASE}/users/carol"],
            "udm_properties": UDM_PROPERTIES,
            "dn": f"uid=alice,cn=schueler,cn=users,ou={SCHOOL},{LDAP_BASE}",
            "url": f"{BASE}/users/alice",
        }
    )


def _school() -> SchoolModel:
    return SchoolModel.parse_obj(
        {
            "name": SCHOOL,
            "display_name": "Demo School",
            "educational_servers": ["dc1"],
            "home_share_file_server": "dc1",
            "udm_properties": UDM_PROPERTIES,
            "dn": f"ou={SCHOOL},{LDAP_BASE}",
            "url": f"{BASE}/schools/{SCHOOL}",
            "ucsschool_roles": [f"school:school:{SCHOOL}"],
        }
    )


def _school_class() -> SchoolClassModel:
    return SchoolClassModel.parse_obj(
        {
            "name": "1a",
            "school": f"{BASE}/schools/{SCHOOL}",
            "description": "Class 1a",
            "users": [f"{BASE}/users/alice"],
            "udm_properties": UDM_PROPERTIES,
            "dn": f"cn={SCHOOL}-1a,cn=klassen,cn=schueler,cn=groups,ou={SCHOOL},{LDAP_BASE}",
            "url": f"{BASE}/classes/{SCHOOL}/1a",
            "ucsschool_roles": [f"school_class:school:{SCHOOL}"],
        }
    )


def _workgroup() -> WorkGroupModel:
    return WorkGroupModel.parse_obj(
        {
            "name": "chess",
            "school": f"{BASE}/schools/{SCHOOL}",
            "users": [f"{BASE}/users/alice"],
            "allowed_email_senders_users": [f"{BASE}/users/alice"],
            "udm_properties": UDM_PROPERTIES,
            "dn": f"cn={SCHOOL}-chess,cn=schueler,cn=groups,ou={SCHOOL},{LDAP_BASE}",
            "url": f"{BASE}/workgroups/{SCHOOL}/chess",
            "ucsschool_roles": [f"workgroup:school:{SCHOOL}"],
        }
    )


def _role() -> RoleModel:
    return RoleModel.parse_obj(
        {"name": "student", "display_name": "student", "url": f"{BASE}/roles/student"}
    )


@pytest.mark.parametrize("build", [_user, _school, _school_class, _workgroup, _role])
def test_model_list_response_matches_the_generic_encoder(build: Callable[[], BaseModel]) -> None:
    models: list[BaseModel] = [build()]

    assert model_list_response(models).body == orjson.dumps(jsonable_encoder(models))


def test_model_list_response_of_nothing_is_an_empty_list() -> None:
    assert model_list_response([]).body == b"[]"
