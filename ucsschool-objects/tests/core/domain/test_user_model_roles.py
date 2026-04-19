from __future__ import annotations

from tests.core.domain.helpers.model_builders import (
    role as build_role,
    school as build_school,
    user as build_user,
)
from ucsschool_objects.core.domain import (
    UNLOADED,
    SchoolMembership,
    UnloadedType,
)


def test_roles_returns_unloaded_when_memberships_unloaded() -> None:
    user = build_user(school_memberships=UNLOADED)
    assert isinstance(user.roles, UnloadedType)


def test_roles_returns_unloaded_when_any_membership_roles_unloaded() -> None:
    school = build_school()
    m1 = SchoolMembership(school=school, is_primary=True, roles=frozenset({build_role("staff")}))
    m2 = SchoolMembership(school=school, is_primary=False, roles=UNLOADED)
    user = build_user(school_memberships=frozenset({m1, m2}))
    assert isinstance(user.roles, UnloadedType)


def test_roles_returns_empty_tuple_when_no_roles() -> None:
    school = build_school()
    membership = SchoolMembership(school=school, is_primary=True, roles=frozenset())
    user = build_user(school_memberships=frozenset({membership}))
    assert user.roles == frozenset()


def test_roles_deduplicates_across_memberships() -> None:
    school = build_school()
    shared = build_role("shared")
    only_first = build_role("only-first")
    only_second = build_role("only-second")
    m1 = SchoolMembership(school=school, is_primary=True, roles=frozenset({shared, only_first}))
    m2 = SchoolMembership(school=school, is_primary=False, roles=frozenset({shared, only_second}))
    user = build_user(school_memberships=frozenset({m1, m2}))
    result = user.roles
    assert isinstance(result, frozenset)
    assert {role.public_id for role in result} == {
        shared.public_id,
        only_first.public_id,
        only_second.public_id,
    }
