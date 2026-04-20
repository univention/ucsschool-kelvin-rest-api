from __future__ import annotations

import uuid
from typing import Any

import pytest
from ucsschool_objects.core.domain import (
    Group,
    GroupValidator,
    Role,
    RoleValidator,
    School,
    SchoolValidator,
    User,
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
        display_name={},
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
        display_name={},
        create_share=False,
        group_type="school_class",
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
    )
    return User(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# School
# ---------------------------------------------------------------------------


class TestSchoolValidation:
    def test_valid_school_is_accepted(self) -> None:
        SchoolValidator.validate(_school())

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="School.name"):
            SchoolValidator.validate(_school(name=""))

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
        with pytest.raises(ValueError, match="Invalid school name"):
            SchoolValidator.validate(_school(name=name))

    @pytest.mark.parametrize("name", ["A", "School1", "My-School", "school_2", "S1-A2_B3"])
    def test_valid_name_formats_are_accepted(self, name: str) -> None:
        SchoolValidator.validate(_school(name=name))

    def test_empty_record_uid_raises(self) -> None:
        with pytest.raises(ValueError, match="School.record_uid"):
            SchoolValidator.validate(_school(record_uid=""))

    def test_empty_source_uid_raises(self) -> None:
        with pytest.raises(ValueError, match="School.source_uid"):
            SchoolValidator.validate(_school(source_uid=""))


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------


class TestRoleValidation:
    def test_valid_role_is_accepted(self) -> None:
        RoleValidator.validate(_role())

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Role.name"):
            RoleValidator.validate(_role(name=""))


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


class TestGroupValidation:
    def test_valid_group_is_accepted(self) -> None:
        GroupValidator.validate(_group())

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Group.name"):
            GroupValidator.validate(_group(name=""))

    def test_empty_record_uid_raises(self) -> None:
        with pytest.raises(ValueError, match="Group.record_uid"):
            GroupValidator.validate(_group(record_uid=""))

    def test_empty_source_uid_raises(self) -> None:
        with pytest.raises(ValueError, match="Group.source_uid"):
            GroupValidator.validate(_group(source_uid=""))

    def test_empty_group_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Group.group_type"):
            GroupValidator.validate(_group(group_type=""))


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class TestUserValidation:
    def test_valid_user_is_accepted(self) -> None:
        UserValidator.validate(_user())

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="User.name"):
            UserValidator.validate(_user(name=""))

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
        with pytest.raises(ValueError, match="invalid characters"):
            UserValidator.validate(_user(name=name))

    @pytest.mark.parametrize("name", ["ends_with_space ", "ends_with_period."])
    def test_name_ending_with_space_or_period_raises(self, name: str) -> None:
        with pytest.raises(ValueError, match="must not end with"):
            UserValidator.validate(_user(name=name))

    def test_name_exceeding_255_chars_raises(self) -> None:
        with pytest.raises(ValueError, match="255"):
            UserValidator.validate(_user(name="a" * 256))

    @pytest.mark.parametrize(
        "name",
        ["CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9", "con", "Con", "nul.txt"],
    )
    def test_windows_reserved_names_raise(self, name: str) -> None:
        with pytest.raises(ValueError, match="reserved Windows name"):
            UserValidator.validate(_user(name=name))

    @pytest.mark.parametrize("name", ["alice", "bob.smith", "COM10", "LPT10", "CONSOLE"])
    def test_non_reserved_names_are_accepted(self, name: str) -> None:
        UserValidator.validate(_user(name=name))

    def test_empty_firstname_raises(self) -> None:
        with pytest.raises(ValueError, match="User.firstname"):
            UserValidator.validate(_user(firstname=""))

    def test_empty_lastname_raises(self) -> None:
        with pytest.raises(ValueError, match="User.lastname"):
            UserValidator.validate(_user(lastname=""))

    def test_empty_record_uid_raises(self) -> None:
        with pytest.raises(ValueError, match="User.record_uid"):
            UserValidator.validate(_user(record_uid=""))

    def test_empty_source_uid_raises(self) -> None:
        with pytest.raises(ValueError, match="User.source_uid"):
            UserValidator.validate(_user(source_uid=""))
