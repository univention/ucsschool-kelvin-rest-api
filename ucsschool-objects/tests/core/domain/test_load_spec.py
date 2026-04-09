from ucsschool_objects.core.domain import LoadSpec


def test_load_spec_includes() -> None:
    load = LoadSpec.from_relations("school", "groups")
    assert load.includes("school")
    assert load.includes("groups")
    assert not load.includes("roles")
