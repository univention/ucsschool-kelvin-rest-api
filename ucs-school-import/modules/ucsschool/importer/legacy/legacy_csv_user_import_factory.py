# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
Factory implementation for import using CSV in legacy format.
"""

from ucsschool.lib.roles import role_pupil, role_staff, role_teacher

from ..default_user_import_factory import DefaultUserImportFactory
from .legacy_csv_reader import LegacyCsvReader
from .legacy_import_user import (
    LegacyImportStaff,
    LegacyImportStudent,
    LegacyImportTeacher,
    LegacyImportTeachersAndStaff,
    LegacyImportUser,
)
from .legacy_new_user_password_csv_exporter import LegacyNewUserPasswordCsvExporter
from .legacy_user_import import LegacyUserImport


class LegacyCsvUserImportFactory(DefaultUserImportFactory):
    def make_reader(self, **kwargs):
        """
        Creates a reader for legacy CSV files.

        :param kwarg: passed to the reader constructor
        :return: a BaseReader object
        :rtype: LegacyCsvReader
        """
        kwargs.update(
            dict(
                filename=self.config["input"]["filename"],
                header_lines=self.config["csv"]["header_lines"],
            )
        )
        return LegacyCsvReader(**kwargs)

    def make_import_user(self, cur_user_roles, *arg, **kwargs):
        """
        Creates a LegacyImportUser of specific type.

        :param func:`list` cur_user_roles: [ucsschool.lib.roles, ..]
        :param func:`list` arg: passed to constructor of created class
        :param dict kwarg: passed to constructor of created class
        :return: object of LegacyImportUser subclass
        :rtype: LegacyImportUser
        """
        if not cur_user_roles:
            return LegacyImportUser(*arg, **kwargs)
        if role_pupil in cur_user_roles:
            return LegacyImportStudent(*arg, **kwargs)
        if role_teacher in cur_user_roles:
            if role_staff in cur_user_roles:
                return LegacyImportTeachersAndStaff(*arg, **kwargs)
            else:
                return LegacyImportTeacher(*arg, **kwargs)
        else:
            return LegacyImportStaff(*arg, **kwargs)

    def make_password_exporter(self, *arg, **kwargs):
        """
        Creates a ResultExporter object that can dump passwords to disk.

        :param func:`list` arg: passed to constructor of created class
        :param dict kwarg: passed to constructor of created class
        :return: ResultExporter object
        :rtype: LegacyNewUserPasswordCsvExporter
        """
        return LegacyNewUserPasswordCsvExporter(*arg, **kwargs)

    def make_user_importer(self, dry_run=True):
        """
        Creates a user importer.

        :param bool dry_run: set to False to actually commit changes to LDAP
        :return: UserImport object
        :rtype: LegacyUserImport
        """
        return LegacyUserImport(dry_run=dry_run)
