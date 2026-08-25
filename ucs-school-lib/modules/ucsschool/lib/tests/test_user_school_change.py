# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
Tests for User.do_school_change() that do not need a joined domain.

Everything the method reaches the directory through is mocked, which leaves the
group bookkeeping it does in between -- the part that used to raise -- as the
only thing under test.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ucsschool.lib.models.user import Staff

LDAP_BASE = "dc=example,dc=test"
OU1 = "ou1"
OU2 = "ou2"


def group_dn(name: str, school: str) -> str:
    return f"cn={name},cn=groups,ou={school},{LDAP_BASE}"


def fake_udm_user(groups, primary_group: str, school: str):
    """A stand-in for the UDM object do_school_change() modifies and saves."""
    props = SimpleNamespace(
        groups=list(groups),
        primaryGroup=primary_group,
        departmentNumber=[school],
        school=[school],
        unixhome="",
        sambahome="",
        profilepath="",
        homedrive="",
        scriptpath="",
    )
    return SimpleNamespace(props=props, save=AsyncMock())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "primary_group_name_in_groups",
    ["Domain Users", "domain users", "DOMAIN USERS"],
    ids=["same_case", "lower_case", "upper_case"],
)
async def test_do_school_change_removes_primary_group_case_insensitively(
    primary_group_name_in_groups: str,
):
    """
    The DN of the primary group can differ in case between a user's 'groups' and
    its 'primaryGroup' property. Removing it from 'groups' must not depend on the
    case, or the school change fails with a ValueError after the user was already
    moved.
    """
    old_primary_group = group_dn(f"Domain Users {OU1}", OU1)
    old_primary_group_in_groups = group_dn(f"{primary_group_name_in_groups} {OU1}", OU1)
    new_primary_group = group_dn(f"Domain Users {OU2}", OU2)
    unrelated_group = group_dn("Domain Users", OU2)

    udm_user = fake_udm_user(
        groups=[old_primary_group_in_groups, unrelated_group],
        primary_group=old_primary_group,
        school=OU1,
    )
    user = Staff(name="test.user", school=OU2, schools=[OU2])
    # remove_from_groups_of_school() leaves the primary group in 'groups' on
    # purpose, because it cannot be removed there through UDM.
    user.remove_from_groups_of_school = AsyncMock()
    user.get_udm_object = AsyncMock(return_value=udm_user)
    user.primary_group_dn = AsyncMock(return_value=new_primary_group)
    user.groups_used = AsyncMock(return_value=[new_primary_group])

    await user.do_school_change(udm_user, MagicMock(), OU1)

    assert old_primary_group_in_groups not in udm_user.props.groups
    assert set(udm_user.props.groups) == {unrelated_group, new_primary_group}
    assert udm_user.props.primaryGroup == new_primary_group
    assert udm_user.props.school == [OU2]
    assert udm_user.props.departmentNumber == [OU2]
    udm_user.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_do_school_change_tolerates_missing_primary_group():
    """A primary group that is not in 'groups' at all is not an error either."""
    new_primary_group = group_dn(f"Domain Users {OU2}", OU2)
    unrelated_group = group_dn("Domain Users", OU2)

    udm_user = fake_udm_user(
        groups=[unrelated_group],
        primary_group=group_dn(f"Domain Users {OU1}", OU1),
        school=OU1,
    )
    user = Staff(name="test.user", school=OU2, schools=[OU2])
    user.remove_from_groups_of_school = AsyncMock()
    user.get_udm_object = AsyncMock(return_value=udm_user)
    user.primary_group_dn = AsyncMock(return_value=new_primary_group)
    user.groups_used = AsyncMock(return_value=[new_primary_group])

    await user.do_school_change(udm_user, MagicMock(), OU1)

    assert set(udm_user.props.groups) == {unrelated_group, new_primary_group}
    assert udm_user.props.primaryGroup == new_primary_group
