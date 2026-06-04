from dataclasses import fields

from ucsschool_objects import LoadSpec, User


def test_load_spec_includes() -> None:
    load = LoadSpec.from_attributes("school", "primary_school")
    assert load.includes("school")
    assert load.includes("primary_school")
    assert not load.includes("groups")


def test_load_spec_from_model_covers_all_fields() -> None:
    load = LoadSpec.from_model(User)
    for f in fields(User):
        assert load.includes(f.name.removeprefix("_"))
    assert load.includes("name")
    assert load.includes("school_memberships")
    assert not load.includes("not_a_field")
