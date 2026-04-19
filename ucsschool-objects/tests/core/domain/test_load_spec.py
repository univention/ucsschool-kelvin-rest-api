from ucsschool_objects.core.domain import LoadSpec


def test_load_spec_includes() -> None:
    load = LoadSpec.from_attributes("school", "primary_school")
    assert load.includes("school")
    assert load.includes("primary_school")
    assert not load.includes("groups")
