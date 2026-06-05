from ucsschool_objects import LoadSpec, User
from ucsschool_objects.core.domain.models import get_properties


def test_load_spec_includes() -> None:
    load = LoadSpec.from_attributes("school", "primary_school")
    assert load.includes("school")
    assert load.includes("primary_school")
    assert not load.includes("groups")


def test_load_spec_from_model_covers_all_fields() -> None:
    load = LoadSpec.from_model(User)
    for property_name in get_properties(User):
        assert load.includes(property_name)
    assert load.includes("name")
    assert load.includes("school_memberships")
    assert not load.includes("not_a_field")
