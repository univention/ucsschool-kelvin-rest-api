from __future__ import annotations

import pytest
from tests.core.domain.helpers.model_builders import school as build_school, user as build_user
from ucsschool_objects.core.domain import (
    UNLOADED,
    SchoolMembership,
    UnloadedType,
)


def test_primary_school_returns_unloaded_when_memberships_unloaded() -> None:
    user = build_user(school_memberships=UNLOADED)
    assert isinstance(user.primary_school, UnloadedType)


def test_primary_school_raises_when_no_primary_membership() -> None:
    school = build_school()
    membership = SchoolMembership(school=school, is_primary=False)
    user = build_user(school_memberships=(membership,))
    with pytest.raises(ValueError, match="no primary school"):
        _ = user.primary_school


def test_primary_school_returns_school_of_primary_membership() -> None:
    primary = build_school("primary")
    secondary = build_school("secondary")
    memberships = (
        SchoolMembership(school=secondary, is_primary=False),
        SchoolMembership(school=primary, is_primary=True),
    )
    user = build_user(school_memberships=memberships)
    assert user.primary_school is primary


def test_primary_school_is_cached() -> None:
    school = build_school()
    membership = SchoolMembership(school=school, is_primary=True)
    user = build_user(school_memberships=(membership,))
    first = user.primary_school
    second = user.primary_school
    assert first is second


def test_primary_school_raises_when_no_memberships() -> None:
    user = build_user(school_memberships=())
    with pytest.raises(ValueError, match="no primary school"):
        _ = user.primary_school
