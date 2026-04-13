# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
ImportUser subclass for import using legacy CSV format.
"""

from ldap.filter import filter_format

from ucsschool.lib.models.user import Staff, Student, Teacher, TeachersAndStaff
from univention.admin.uexceptions import noObject

from ..exceptions import MissingUid, UnknownAction
from ..models.import_user import (
    ImportStaff,
    ImportStudent,
    ImportTeacher,
    ImportTeachersAndStaff,
    ImportUser,
)


class LegacyImportUser(ImportUser):
    def make_disabled(self):
        """
        Handled in LegacyCsvReader.handle_input(). Overwriting here, so
        changes in ImportUser do not change behavior of LegacyImportUser.
        """

    def make_firstname(self):
        """
        Do not normalize given names.
        """
        if self.firstname:
            return
        elif "firstname" in self.config["scheme"]:
            self.firstname = self.format_from_scheme("firstname", self.config["scheme"]["firstname"])
        else:
            self.firstname = ""

    def make_lastname(self):
        """
        Do not normalize family names.
        """
        if self.lastname:
            return
        elif "lastname" in self.config["scheme"]:
            self.lastname = self.format_from_scheme("lastname", self.config["scheme"]["lastname"])
        else:
            self.lastname = ""

    def make_username(self):
        super(LegacyImportUser, self).make_username()
        self.old_name = self.name  # for LegacyNewUserPasswordCsvExporter.serialize()
        self.name = self.name.lower()

    def validate(self, lo, validate_unlikely_changes=False, check_username=False):
        """
        Action must already be configured in CSV.
        """
        if self.action and self.action not in ["A", "D", "M"]:
            raise UnknownAction("Unknown action '{}'.".format(self.action))
        super(LegacyImportUser, self).validate(lo, validate_unlikely_changes, check_username)

    def _check_username_uniqueness(self):  # type: () -> None
        """
        Check that :py:attr:`self.name` is not already in use by another user.

        :raises UniqueIdError: if username is already taken by another user
        """
        uut = self._all_usernames.get(self.name)
        if uut and uut.dn != self.dn:
            self.add_error(
                "name",
                "Username {!r} is already in use by {!r}.".format(
                    self.name, self._all_usernames[self.name]
                ),
            )

    @classmethod
    def get_by_import_id_or_username(
        cls, connection, source_uid, record_uid, username, superordinate=None
    ):
        """
        Retrieve a LegacyImportUser.
        Will find it using either source_uid and record_uid or if unset
        with the username.

        :param univention.admin.uldap.access connection: uldap object
        :param str source_uid: source DB identifier
        :param str record_uid: source record identifier
        :param str username: username
        :param str superordinate: superordinate
        :return: object of :py:class:`ImportUser` subclass loaded from LDAP or raises noObject
        :rtype: ImportUser
        :raises noObject: if no user object was found
        """
        if not (source_uid and record_uid) and not username:
            raise MissingUid(
                "Username or source_uid and record_uid are not set (username={!r} source_uid={!r}"
                "record_uid={!r}).".format(username, source_uid, record_uid)
            )

        oc_filter = cls.get_ldap_filter_for_user_role()
        filter_s = filter_format(
            "(&{ocs}"
            "(|"
            "(&(ucsschoolSourceUID=%s)(ucsschoolRecordUID=%s))"
            "(&(!(ucsschoolSourceUID=*))(!(ucsschoolRecordUID=*))(uid=%s))"
            "))".format(ocs=oc_filter),
            (source_uid, record_uid, username),
        )
        obj = cls.get_only_udm_obj(connection, filter_s, superordinate=superordinate)
        if not obj:
            raise noObject(
                "No {} with source_uid={!r} and record_uid={!r} or username={!r} found.".format(
                    cls.config.get("user_role", "user"), source_uid, record_uid, username
                )
            )
        return cls.from_udm_obj(obj, None, connection)

    @classmethod
    def get_class_for_udm_obj(cls, udm_obj, school):
        """
        IMPLEMENTME if you subclass!

        :param univention.admin.handlers.simpleLdap udm_obj: UDM user instance
        :param str school: name of OU
        """
        klass = super(LegacyImportUser, cls).get_class_for_udm_obj(udm_obj, school)
        if issubclass(klass, TeachersAndStaff):
            return LegacyImportTeachersAndStaff
        elif issubclass(klass, Teacher):
            return LegacyImportTeacher
        elif issubclass(klass, Staff):
            return LegacyImportStaff
        elif issubclass(klass, Student):
            return LegacyImportStudent
        else:
            return None


class LegacyImportStudent(LegacyImportUser, ImportStudent):
    pass


class LegacyImportStaff(LegacyImportUser, ImportStaff):
    pass


class LegacyImportTeacher(LegacyImportUser, ImportTeacher):
    pass


class LegacyImportTeachersAndStaff(LegacyImportUser, ImportTeachersAndStaff):
    pass
