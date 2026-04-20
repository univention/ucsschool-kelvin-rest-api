from __future__ import annotations

from tests.core.domain.helpers.model_builders import role as build_role, school as build_school
from ucsschool_objects.core.domain import (
    SchoolMembership,
)


def test_school_membership_holds_roles() -> None:
    school = build_school()
    role1 = build_role("teacher")
    role2 = build_role("student")
    membership = SchoolMembership(
        school=school, is_primary=True, roles=frozenset({role1, role2}), groups=frozenset()
    )
    roles = membership.roles
    assert len(roles) == 2
    names = {r.name for r in roles}
    assert names == {"teacher", "student"}
