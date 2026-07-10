# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from ucsschool_objects import SchoolMembership

from .helpers.model_builders import role as build_role, school as build_school


def test_school_membership_holds_roles() -> None:
    school = build_school()
    role1 = build_role("teacher")
    role2 = build_role("student")
    membership = SchoolMembership(
        school=school, is_primary=True, roles=set({role1, role2}), groups=set()
    )
    roles = membership.roles
    assert len(roles) == 2
    names = {r.name for r in roles}
    assert names == {"teacher", "student"}
