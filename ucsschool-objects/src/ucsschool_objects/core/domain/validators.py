from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Group, Role, School, User

# Ported from ucs-school-lib/modules/ucsschool/lib/models/attributes.py: SchoolName
_SCHOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9](([a-zA-Z0-9\-_]*)([a-zA-Z0-9]$))?$")

# Ported from ucs-school-lib/modules/ucsschool/lib/models/attributes.py: is_valid_win_directory_name
_WIN_INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
_WIN_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM0",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT0",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)


class SchoolValidator:
    @staticmethod
    def validate(school: School) -> None:
        if not school.name:
            raise ValueError("School.name must not be empty.")
        if not _SCHOOL_NAME_RE.match(school.name):
            raise ValueError(
                f"Invalid school name {school.name!r}: must start and end with an alphanumeric "
                "character and only contain letters, digits, hyphens, or underscores."
            )
        if not school.record_uid:
            raise ValueError("School.record_uid must not be empty.")
        if not school.source_uid:
            raise ValueError("School.source_uid must not be empty.")
        # TODO: validate that educational_servers and administrative_servers do not overlap
        #   (dc_name != dc_name_administrative). Needs LDAP to resolve server names.
        #   See ucs-school-lib/modules/ucsschool/lib/models/school.py: School.validate()
        # TODO: validate that educational DC is not a Backup or Primary Directory Node.
        #   Needs LDAP search for univentionServerRole.
        #   See ucs-school-lib/modules/ucsschool/lib/models/school.py: School.validate()


class RoleValidator:
    @staticmethod
    def validate(role: Role) -> None:
        if not role.name:
            raise ValueError("Role.name must not be empty.")


class GroupValidator:
    @staticmethod
    def validate(group: Group) -> None:
        if not group.name:
            raise ValueError("Group.name must not be empty.")
        if not group.record_uid:
            raise ValueError("Group.record_uid must not be empty.")
        if not group.source_uid:
            raise ValueError("Group.source_uid must not be empty.")
        if not group.roles:
            raise ValueError("Group.roles must not be empty.")
        # TODO: validate group name against gid syntax (alphanumeric + limited special chars).
        #   Currently skipped because it requires the UDM syntax parser (univention.admin.syntax.gid).
        #   See ucs-school-lib/modules/ucsschool/lib/models/attributes.py: GroupName
        # TODO: for school_class roles, validate that name starts with "{school.name}-".
        #   Requires school to be loaded (not UnloadedType).
        #   See ucs-school-lib/modules/ucsschool/lib/models/group.py: SchoolClass.validate()


class UserValidator:
    @staticmethod
    def validate(user: User) -> None:
        if not user.name:
            raise ValueError("User.name must not be empty.")
        if _WIN_INVALID_CHARS_RE.search(user.name):
            raise ValueError(f"User.name {user.name!r} contains invalid characters.")
        if user.name[-1] in (" ", "."):
            raise ValueError(f"User.name {user.name!r} must not end with a space or period.")
        if len(user.name) > 255:
            raise ValueError("User.name must not exceed 255 characters.")
        if user.name.split(".")[0].upper() in _WIN_RESERVED_NAMES:
            raise ValueError(f"User.name {user.name!r} is a reserved Windows name.")
        if not user.firstname:
            raise ValueError("User.firstname must not be empty.")
        if not user.lastname:
            raise ValueError("User.lastname must not be empty.")
        if not user.record_uid:
            raise ValueError("User.record_uid must not be empty.")
        if not user.source_uid:
            raise ValueError("User.source_uid must not be empty.")
        # TODO: validate username against uid_umlauts syntax (allows umlauts, specific char set).
        #   Currently skipped because it requires the UDM syntax parser
        #   (univention.admin.syntax.uid_umlauts).
        #   See ucs-school-lib/modules/ucsschool/lib/models/attributes.py: Username
        # TODO: validate email format and domain via primaryEmailAddressValidDomain syntax.
        #   Currently skipped because it requires the UDM syntax parser.
        #   See ucs-school-lib/modules/ucsschool/lib/models/attributes.py: Email
        # TODO: validate email uniqueness across all users.
        #   Requires LDAP search:
        #   (&(univentionObjectType=users/user)(!(uid=<name>))(mailPrimaryAddress=<email>))
        #   See ucs-school-lib/modules/ucsschool/lib/models/user.py: User.validate()
        # TODO: validate that all users in legal_guardians actually exist.
        #   Requires LDAP/repository lookup.
        #   See ucs-school-lib/modules/ucsschool/lib/models/user.py: Student.validate()
        # TODO: validate that all users in legal_wards actually exist.
        #   Requires LDAP/repository lookup.
        #   See ucs-school-lib/modules/ucsschool/lib/models/user.py: LegalGuardian.validate()
