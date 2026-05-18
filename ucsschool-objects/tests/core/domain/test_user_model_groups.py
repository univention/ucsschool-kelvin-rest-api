from __future__ import annotations

from typing import cast
from uuid import UUID

import pytest
from tests.core.domain.helpers.model_builders import (
    school as build_school,
    school_class as build_school_class,
    user as build_user,
)
from ucsschool_objects.core.domain import (
    UNLOADED,
    SchoolMembership,
)


def test_groups_raises_when_memberships_unloaded() -> None:
    user = build_user(school_memberships=UNLOADED)
    with pytest.raises(ValueError, match="User.school_memberships is not loaded"):
        _ = user.groups


def test_groups_returns_empty_tuple_when_no_groups() -> None:
    school = build_school()
    membership = SchoolMembership(school=school, is_primary=True, roles=set(), groups=set())
    user = build_user(school_memberships={cast(UUID, school.public_id): membership})
    assert user.groups == set()


def test_groups_deduplicates_across_memberships() -> None:
    school1 = build_school("school1")
    school2 = build_school("school2")
    g_shared = build_school_class("shared")
    g_only_first = build_school_class("only_first")
    g_only_second = build_school_class("only_second")
    m1 = SchoolMembership(
        school=school1, is_primary=True, roles=set(), groups=set({g_shared, g_only_first})
    )
    m2 = SchoolMembership(
        school=school2, is_primary=False, roles=set(), groups=set({g_shared, g_only_second})
    )
    user = build_user(
        school_memberships={
            cast(UUID, m1.school.public_id): m1,
            cast(UUID, m2.school.public_id): m2,
        }
    )
    result = user.groups
    assert isinstance(result, set)
    assert len(result) == 3
    public_ids = {g.public_id for g in result}
    assert g_shared.public_id in public_ids
    assert g_only_first.public_id in public_ids
    assert g_only_second.public_id in public_ids


def test_groups_is_cached() -> None:
    school = build_school()
    g = build_school_class()
    membership = SchoolMembership(school=school, is_primary=True, roles=set(), groups=set({g}))
    user = build_user(school_memberships={cast(UUID, school.public_id): membership})
    first = user.groups
    second = user.groups
    assert first == second
