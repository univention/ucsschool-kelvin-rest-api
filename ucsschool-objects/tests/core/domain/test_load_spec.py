from typing import Hashable, cast

import pytest
from ucsschool_objects import Group, LoadSpec, Role, School, SchoolMembership, User
from ucsschool_objects.core.domain.models import (
    SerializableDomainObjectType,
    get_properties,
)


def test_load_spec_includes() -> None:
    load = LoadSpec.from_attributes("school", "primary_school")
    assert load.includes("school")
    assert load.includes("primary_school")
    assert not load.includes("groups")


@pytest.mark.parametrize(
    "model",
    [School, Role, Group, SchoolMembership, User],
    ids=["school", "role", "group", "school_membership", "user"],
)
def test_load_spec_from_model_covers_all_fields(
    model: SerializableDomainObjectType,
) -> None:
    load = LoadSpec.from_model(cast(Hashable, model))
    for property_name in get_properties(model):
        assert load.includes(property_name)
    assert not load.includes("not_a_field")


@pytest.mark.parametrize(
    "model",
    [School, Role, Group, SchoolMembership, User],
    ids=["school", "role", "group", "school_membership", "user"],
)
def test_load_spec_from_model_is_cached_per_model(
    model: SerializableDomainObjectType,
) -> None:
    assert LoadSpec.from_model(cast(Hashable, model)) is LoadSpec.from_model(cast(Hashable, model))
