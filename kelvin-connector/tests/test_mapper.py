from dataclasses import fields

import pytest
from kelvin_connector.property_mapper import (
    UDM_USER_PROPERTY_MAPPING,
    UDMPropertyMapper,
)
from ucsschool_objects.core.domain import User

test_data = {
    "username": "demo_parent",
    "firstname": "Demo",
    "lastname": "Legal Guardian3",
    "userexpiry": None,
    "passwordexpiry": None,
    "disabled": False,
    "e-mail": ["demo_parent@demoschool.example.com"],
    "school": ["DEMOSCHOOL"],
    "ucsschoolSourceUID": "DEMOID",
    "ucsschoolRecordUID": "demo_parent",
    "ucsschoolRole": ["legal_guardian:school:DEMOSCHOOL"],
    "ucsschoolLegalWard": ["uid=demo_student,cn=schueler,cn=users,ou=DEMOSCHOOL,dc=ucsschool,dc=test"],
}


def test_user_property_mapper():
    udm_property_mapper = UDMPropertyMapper()
    udm_property_mapper.register_map(UDM_USER_PROPERTY_MAPPING)

    def invert_hook(value: bool):
        return not value

    udm_property_mapper.register_hook("disabled", invert_hook)
    mapped_test_data = udm_property_mapper.map(test_data)
    assert mapped_test_data == {
        "name": "demo_parent",
        "firstname": "Demo",
        "lastname": "Legal Guardian3",
        "expiration_date": None,
        "active": True,
        "email": ["demo_parent@demoschool.example.com"],
        "school_memberships": ["DEMOSCHOOL"],
        "source_uid": "DEMOID",
        "record_uid": "demo_parent",
        "legal_wards": ["uid=demo_student,cn=schueler,cn=users,ou=DEMOSCHOOL,dc=ucsschool,dc=test"],
    }


def test_fields_equal_mapping():
    user_fields = fields(User)
    user_fields = set([user_field.name for user_field in user_fields])
    user_fields.remove("public_id")
    assert user_fields == set(UDM_USER_PROPERTY_MAPPING.values())


def test_register_map_raises_on_duplicate_source_key():
    mapper = UDMPropertyMapper()
    mapper.register_map({"key_a": "val_a"})
    with pytest.raises(ValueError, match="Source key 'key_a' is already registered"):
        mapper.register_map({"key_a": "val_b"})


def test_register_map_raises_on_duplicate_target_key():
    mapper = UDMPropertyMapper()
    mapper.register_map({"key_a": "val_a"})
    with pytest.raises(ValueError, match="Target key 'val_a' is already registered"):
        mapper.register_map({"key_b": "val_a"})


def test_register_hook_raises_on_unregistered_source_key():
    mapper = UDMPropertyMapper()
    with pytest.raises(ValueError, match="Source key 'missing' is not registered"):
        mapper.register_hook("missing", lambda x: x)
