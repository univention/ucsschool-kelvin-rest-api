# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import uuid
from typing import Any

import pytest
from ucsschool_objects import (
    UNLOADED,
    Group,
    Role,
    School,
    User,
)
from ucsschool_objects.core.domain.validators import (
    GroupValidator,
    RoleValidator,
    SchoolValidator,
    UserValidator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _school(**overrides: Any) -> School:
    defaults = dict(
        public_id=uuid.uuid4(),
        record_uid="r1",
        source_uid="s1",
        name="Testschool",
        display_name="",
        educational_servers=frozenset({"srv"}),
        administrative_servers=frozenset(),
        class_share_file_server=None,
        home_share_file_server=None,
    )
    return School(**{**defaults, **overrides})


def _role(**overrides: Any) -> Role:
    defaults = dict(public_id=uuid.uuid4(), name="teacher", display_name={})
    return Role(**{**defaults, **overrides})


def _group(**overrides: Any) -> Group:
    defaults = dict(
        public_id=uuid.uuid4(),
        record_uid="rg",
        source_uid="sg",
        name="Testschool-classA",
        display_name="",
        create_share=False,
        roles="school_class",
        email=None,
        allowed_email_senders_users=UNLOADED,
        allowed_email_senders_groups=UNLOADED,
        members=UNLOADED,
        member_roles=UNLOADED,
        school=UNLOADED,
    )
    return Group(**{**defaults, **overrides})


def _user(**overrides: Any) -> User:
    defaults = dict(
        public_id=uuid.uuid4(),
        record_uid="ru",
        source_uid="su",
        name="testuser",
        firstname="Test",
        lastname="User",
        email=None,
        birthday=None,
        expiration_date=None,
        active=True,
        school_memberships=UNLOADED,
        legal_wards=UNLOADED,
        legal_guardians=UNLOADED,
    )
    return User(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# School
# ---------------------------------------------------------------------------


class TestSchoolValidation:
    def test_valid_school_is_accepted(self) -> None:
        SchoolValidator.validate(_school())

    def test_empty_name_raises(self) -> None:
        school = _school(name="")
        with pytest.raises(ValueError, match="School.name"):
            SchoolValidator.validate(school)

    @pytest.mark.parametrize(
        "name",
        [
            "  ",
            "-startswith-dash",
            "ends-with-dash-",
            "has space",
            "has!special",
            "_starts_with_underscore",
        ],
    )
    def test_invalid_name_format_raises(self, name: str) -> None:
        school = _school(name=name)
        with pytest.raises(ValueError, match="Invalid school name"):
            SchoolValidator.validate(school)

    @pytest.mark.parametrize("name", ["A", "School1", "My-School", "school_2", "S1-A2_B3"])
    def test_valid_name_formats_are_accepted(self, name: str) -> None:
        SchoolValidator.validate(_school(name=name))

    def test_empty_record_uid_raises(self) -> None:
        school = _school(record_uid="")
        with pytest.raises(ValueError, match="School.record_uid"):
            SchoolValidator.validate(school)

    def test_empty_source_uid_raises(self) -> None:
        school = _school(source_uid="")
        with pytest.raises(ValueError, match="School.source_uid"):
            SchoolValidator.validate(school)


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------


class TestRoleValidation:
    def test_valid_role_is_accepted(self) -> None:
        RoleValidator.validate(_role())

    def test_empty_name_raises(self) -> None:
        role = _role(name="")
        with pytest.raises(ValueError, match="Role.name"):
            RoleValidator.validate(role)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


class TestGroupValidation:
    def test_valid_group_is_accepted(self) -> None:
        GroupValidator.validate(_group())

    def test_empty_name_raises(self) -> None:
        group = _group(name="")
        with pytest.raises(ValueError, match="Group.name"):
            GroupValidator.validate(group)

    def test_empty_record_uid_raises(self) -> None:
        group = _group(record_uid="")
        with pytest.raises(ValueError, match="Group.record_uid"):
            GroupValidator.validate(group)

    def test_empty_source_uid_raises(self) -> None:
        group = _group(source_uid="")
        with pytest.raises(ValueError, match="Group.source_uid"):
            GroupValidator.validate(group)

    def test_empty_roles_raises(self) -> None:
        group = _group(roles="")
        with pytest.raises(ValueError, match="Group.roles"):
            GroupValidator.validate(group)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class TestUserValidation:
    def test_valid_user_is_accepted(self) -> None:
        UserValidator.validate(_user())

    def test_empty_name_raises(self) -> None:
        user = _user(name="")
        with pytest.raises(ValueError, match="User.name"):
            UserValidator.validate(user)

    @pytest.mark.parametrize(
        "name",
        [
            'has"quote',
            "has/slash",
            "has\\backslash",
            "has:colon",
            "has*star",
            "has?question",
            "has<less",
            "has>greater",
            "has|pipe",
            "has\x01control",
        ],
    )
    def test_invalid_characters_in_name_raises(self, name: str) -> None:
        user = _user(name=name)
        with pytest.raises(ValueError, match="invalid characters"):
            UserValidator.validate(user)

    @pytest.mark.parametrize("name", ["ends_with_space ", "ends_with_period."])
    def test_name_ending_with_space_or_period_raises(self, name: str) -> None:
        user = _user(name=name)
        with pytest.raises(ValueError, match="must not end with"):
            UserValidator.validate(user)

    def test_name_exceeding_255_chars_raises(self) -> None:
        user = _user(name="a" * 256)
        with pytest.raises(ValueError, match="255"):
            UserValidator.validate(user)

    @pytest.mark.parametrize(
        "name",
        ["CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9", "con", "Con", "nul.txt"],
    )
    def test_windows_reserved_names_raise(self, name: str) -> None:
        user = _user(name=name)
        with pytest.raises(ValueError, match="reserved Windows name"):
            UserValidator.validate(user)

    @pytest.mark.parametrize("name", ["alice", "bob.smith", "COM10", "LPT10", "CONSOLE"])
    def test_non_reserved_names_are_accepted(self, name: str) -> None:
        UserValidator.validate(_user(name=name))

    def test_empty_firstname_raises(self) -> None:
        user = _user(firstname="")
        with pytest.raises(ValueError, match="User.firstname"):
            UserValidator.validate(user)

    def test_empty_lastname_raises(self) -> None:
        user = _user(lastname="")
        with pytest.raises(ValueError, match="User.lastname"):
            UserValidator.validate(user)

    def test_empty_record_uid_raises(self) -> None:
        user = _user(record_uid="")
        with pytest.raises(ValueError, match="User.record_uid"):
            UserValidator.validate(user)

    def test_empty_source_uid_raises(self) -> None:
        user = _user(source_uid="")
        with pytest.raises(ValueError, match="User.source_uid"):
            UserValidator.validate(user)
