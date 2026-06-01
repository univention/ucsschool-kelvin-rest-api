from __future__ import annotations

from typing import cast
from uuid import UUID

import pytest
from tests.core.domain.helpers.model_builders import school as build_school, user as build_user
from ucsschool_objects import (
    UNLOADED,
    SchoolMembership,
)


def test_primary_school_raises_when_memberships_unloaded() -> None:
    user = build_user(school_memberships=UNLOADED)
    with pytest.raises(ValueError, match="User.school_memberships is not loaded"):
        _ = user.primary_school


def test_primary_school_raises_when_no_primary_membership() -> None:
    school = build_school()
    membership = SchoolMembership(school=school, is_primary=False, roles=set(), groups=set())
    user = build_user(school_memberships={cast(UUID, school.public_id): membership})
    with pytest.raises(ValueError, match="no primary school"):
        _ = user.primary_school


def test_primary_school_returns_school_of_primary_membership() -> None:
    primary = build_school("primary")
    secondary = build_school("secondary")
    memberships = {
        cast(UUID, secondary.public_id): SchoolMembership(
            school=secondary, is_primary=False, roles=set(), groups=set()
        ),
        cast(UUID, primary.public_id): SchoolMembership(
            school=primary, is_primary=True, roles=set(), groups=set()
        ),
    }
    user = build_user(school_memberships=memberships)
    assert user.primary_school is primary


def test_primary_school_is_cached() -> None:
    school = build_school()
    membership = SchoolMembership(school=school, is_primary=True, roles=set(), groups=set())
    user = build_user(school_memberships={cast(UUID, school.public_id): membership})
    first = user.primary_school
    second = user.primary_school
    assert first == second


def test_primary_school_raises_when_no_memberships() -> None:
    user = build_user(school_memberships={})
    with pytest.raises(ValueError, match="no primary school"):
        _ = user.primary_school
