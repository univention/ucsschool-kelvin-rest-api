# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
Tests for User.do_school_change() that do not need a joined domain.

Everything the method reaches the directory through is mocked, which leaves the
group bookkeeping it does in between -- the part that used to raise -- as the
only thing under test.
"""

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from ucsschool.lib.models.user import Staff
from udm_rest_client import UDM, UdmObject

LDAP_BASE = "dc=example,dc=test"
OU1 = "ou1"
OU2 = "ou2"


def group_dn(name: str, school: str) -> str:
    return f"cn={name},cn=groups,ou={school},{LDAP_BASE}"


class FakeUdmUserProps:
    """The subset of users/user properties do_school_change() writes to."""

    def __init__(self, groups: list[str], primary_group: str, school: str) -> None:
        self.groups: list[str] = list(groups)
        self.primaryGroup: str = primary_group  # noqa: N815  (UDM property name)
        self.departmentNumber: list[str] = [school]
        self.school: list[str] = [school]
        self.unixhome: str = ""
        self.sambahome: str = ""
        self.profilepath: str = ""
        self.homedrive: str = ""
        self.scriptpath: str = ""


class FakeUdmUser:
    """A stand-in for the UDM object do_school_change() modifies and saves."""

    def __init__(self, groups: list[str], primary_group: str, school: str) -> None:
        self.props: FakeUdmUserProps = FakeUdmUserProps(groups, primary_group, school)
        self.save: AsyncMock = AsyncMock()


def user_for(udm_user: FakeUdmUser, new_primary_group: str) -> Staff:
    """A staff user whose every access to the directory is mocked away."""
    user = Staff(name="test.user", school=OU2, schools=[OU2])
    # remove_from_groups_of_school() leaves the primary group in 'groups' on
    # purpose, because it cannot be removed there through UDM.
    user.remove_from_groups_of_school = AsyncMock()
    user.get_udm_object = AsyncMock(return_value=udm_user)
    user.primary_group_dn = AsyncMock(return_value=new_primary_group)
    user.groups_used = AsyncMock(return_value=[new_primary_group])
    return user


async def change_school(user: Staff, udm_user: FakeUdmUser, old_school: str) -> None:
    # FakeUdmUser only implements the handful of properties the method touches.
    udm_obj = cast(UdmObject, cast(object, udm_user))
    await user.do_school_change(udm_obj, cast(UDM, MagicMock()), old_school)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "primary_group_name_in_groups",
    ["Domain Users", "domain users", "DOMAIN USERS"],
    ids=["same_case", "lower_case", "upper_case"],
)
async def test_do_school_change_removes_primary_group_case_insensitively(
    primary_group_name_in_groups: str,
) -> None:
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

    udm_user = FakeUdmUser(
        groups=[old_primary_group_in_groups, unrelated_group],
        primary_group=old_primary_group,
        school=OU1,
    )
    await change_school(user_for(udm_user, new_primary_group), udm_user, OU1)

    assert old_primary_group_in_groups not in udm_user.props.groups
    assert set(udm_user.props.groups) == {unrelated_group, new_primary_group}
    assert udm_user.props.primaryGroup == new_primary_group
    assert udm_user.props.school == [OU2]
    assert udm_user.props.departmentNumber == [OU2]
    udm_user.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_do_school_change_tolerates_missing_primary_group() -> None:
    """A primary group that is not in 'groups' at all is not an error either."""
    new_primary_group = group_dn(f"Domain Users {OU2}", OU2)
    unrelated_group = group_dn("Domain Users", OU2)

    udm_user = FakeUdmUser(
        groups=[unrelated_group],
        primary_group=group_dn(f"Domain Users {OU1}", OU1),
        school=OU1,
    )
    await change_school(user_for(udm_user, new_primary_group), udm_user, OU1)

    assert set(udm_user.props.groups) == {unrelated_group, new_primary_group}
    assert udm_user.props.primaryGroup == new_primary_group
