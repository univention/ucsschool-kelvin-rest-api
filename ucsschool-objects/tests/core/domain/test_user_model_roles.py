from __future__ import annotations

from typing import cast
from uuid import UUID

import pytest
from tests.core.domain.helpers.model_builders import (
    role as build_role,
    school as build_school,
    user as build_user,
)
from ucsschool_objects.core.domain import (
    UNLOADED,
    SchoolMembership,
)


def test_roles_raises_when_memberships_unloaded() -> None:
    user = build_user(school_memberships=UNLOADED)
    with pytest.raises(ValueError, match="User.school_memberships is not loaded"):
        _ = user.roles


def test_roles_returns_empty_tuple_when_no_roles() -> None:
    school = build_school()
    membership = SchoolMembership(school=school, is_primary=True, roles=set(), groups=set())
    user = build_user(school_memberships={cast(UUID, school.public_id): membership})
    assert user.roles == set()


def test_roles_deduplicates_across_memberships() -> None:
    school1 = build_school("school1")
    school2 = build_school("school2")
    shared = build_role("shared")
    only_first = build_role("only-first")
    only_second = build_role("only-second")
    m1 = SchoolMembership(school=school1, is_primary=True, roles=set({shared, only_first}), groups=set())
    m2 = SchoolMembership(
        school=school2, is_primary=False, roles=set({shared, only_second}), groups=set()
    )
    user = build_user(
        school_memberships={
            cast(UUID, m1.school.public_id): m1,
            cast(UUID, m2.school.public_id): m2,
        }
    )
    result = user.roles
    assert isinstance(result, set)
    assert {role.public_id for role in result} == {
        shared.public_id,
        only_first.public_id,
        only_second.public_id,
    }
