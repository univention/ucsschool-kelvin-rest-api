# Copyright 2026 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

"""Unit tests for the pure ``_user_to_model`` helpers in the v2 user router.

These exercise the group-classification logic in isolation, building real
domain objects (``User``/``Group``/``Role``/``School``) instead of talking to a
live backend. The full ``_user_to_model`` path (URL building, model assembly)
remains covered by the integration tests in ``test_route_user.py``.
"""

import uuid

from ucsschool_objects import UNLOADED, Group, Role, School, SchoolMembership, User

from ucsschool.kelvin.routers.v2.user import _school_classes_and_workgroups


def _group(name: str, school: str, *roles: str) -> Group:
    """Build a ``Group`` carrying only the fields the helper reads.

    The helper touches ``group.name``, ``group.school.name`` and
    ``group.roles[].name``; everything else is left ``UNLOADED``.
    """
    return Group(
        public_id=uuid.uuid4(),
        name=name,
        school=School(public_id=uuid.uuid4(), name=school),
        roles={Role(public_id=uuid.uuid4(), name=role) for role in roles},
    )


def _user(*groups: Group) -> User:
    # ``user.groups`` aggregates the groups of every school membership and
    # returns a set, so the per-school lists are built in arbitrary order; one
    # membership holding all groups is enough to exercise the helper (and guards
    # the "sort for deterministic output" behaviour).
    school_id = uuid.uuid4()
    membership = SchoolMembership(
        school=School(public_id=school_id, name="DEMOSCHOOL"),
        is_primary=True,
        roles=set(),
        groups=set(groups),
    )
    return User(
        public_id=uuid.uuid4(),
        record_uid=UNLOADED,
        source_uid=UNLOADED,
        name=UNLOADED,
        firstname=UNLOADED,
        lastname=UNLOADED,
        active=UNLOADED,
        school_memberships={school_id: membership},
        legal_wards=UNLOADED,
        legal_guardians=UNLOADED,
    )


def test_no_groups_yields_empty_dicts() -> None:
    school_classes, workgroups = _school_classes_and_workgroups(_user())
    assert school_classes == {}
    assert workgroups == {}


def test_school_class_and_workgroup_are_split_by_role() -> None:
    user = _user(
        _group("DEMOSCHOOL-1a", "DEMOSCHOOL", "school_class"),
        _group("DEMOSCHOOL-chess", "DEMOSCHOOL", "workgroup"),
    )
    school_classes, workgroups = _school_classes_and_workgroups(user)
    assert school_classes == {"DEMOSCHOOL": ["1a"]}
    assert workgroups == {"DEMOSCHOOL": ["chess"]}


def test_relative_name_strips_only_the_school_prefix_with_multiple_hyphens() -> None:
    # Regression guard against the old ``split("-")[1]`` which mangled relative
    # names that themselves contain hyphens.
    user = _user(
        _group("DEMOSCHOOL-7-grade-a", "DEMOSCHOOL", "school_class"),
        _group("DEMOSCHOOL-robotics-club-2024", "DEMOSCHOOL", "workgroup"),
    )
    school_classes, workgroups = _school_classes_and_workgroups(user)
    assert school_classes == {"DEMOSCHOOL": ["7-grade-a"]}
    assert workgroups == {"DEMOSCHOOL": ["robotics-club-2024"]}


def test_relative_name_when_school_name_contains_a_hyphen() -> None:
    user = _user(_group("my-school-1a", "my-school", "school_class"))
    school_classes, _ = _school_classes_and_workgroups(user)
    assert school_classes == {"my-school": ["1a"]}


def test_relative_name_strips_prefix_only_not_recurring_substring() -> None:
    # The school-name fragment may reappear inside the relative name; only the
    # leading prefix must be stripped (guards against a global .replace()).
    user = _user(_group("a-a-1", "a", "school_class"))
    school_classes, _ = _school_classes_and_workgroups(user)
    assert school_classes == {"a": ["a-1"]}


def test_groups_are_grouped_per_school() -> None:
    user = _user(
        _group("SCHOOL1-1a", "SCHOOL1", "school_class"),
        _group("SCHOOL2-2b", "SCHOOL2", "school_class"),
    )
    school_classes, workgroups = _school_classes_and_workgroups(user)
    assert school_classes == {"SCHOOL1": ["1a"], "SCHOOL2": ["2b"]}
    assert workgroups == {}


def test_per_school_lists_are_sorted_deterministically() -> None:
    user = _user(
        _group("DEMOSCHOOL-3c", "DEMOSCHOOL", "school_class"),
        _group("DEMOSCHOOL-1a", "DEMOSCHOOL", "school_class"),
        _group("DEMOSCHOOL-2b", "DEMOSCHOOL", "school_class"),
    )
    school_classes, _ = _school_classes_and_workgroups(user)
    assert school_classes == {"DEMOSCHOOL": ["1a", "2b", "3c"]}


def test_schools_without_class_or_workgroup_are_not_pre_seeded() -> None:
    # A group with neither role must not create an (empty) entry, matching v1.
    user = _user(
        _group("DEMOSCHOOL-domain-users", "DEMOSCHOOL", "some_other_role"),
        _group("DEMOSCHOOL-1a", "DEMOSCHOOL", "school_class"),
    )
    school_classes, workgroups = _school_classes_and_workgroups(user)
    assert school_classes == {"DEMOSCHOOL": ["1a"]}
    assert workgroups == {}


def test_group_with_both_roles_lands_in_both_mappings() -> None:
    user = _user(_group("DEMOSCHOOL-hybrid", "DEMOSCHOOL", "school_class", "workgroup"))
    school_classes, workgroups = _school_classes_and_workgroups(user)
    assert school_classes == {"DEMOSCHOOL": ["hybrid"]}
    assert workgroups == {"DEMOSCHOOL": ["hybrid"]}
