# -*- coding: utf-8 -*-
#
# Univention UCS@school
# Copyright 2016-2021 Univention GmbH
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

"""
Write the result of a user import job to a CSV file.
"""

from ucsschool.lib.roles import role_pupil

from ..exceptions import UcsSchoolImportError
from ..factory import Factory
from .result_exporter import ResultExporter


class UserImportCsvResultExporter(ResultExporter):
    """
    Export the results of the user import to a CSV file.
    """

    field_names = (
        "line",
        "success",
        "error",
        "action",
        "role",
        "username",
        "schools",
        "firstname",
        "lastname",
        "birthday",
        "email",
        "disabled",
        "classes",
        "source_uid",
        "record_uid",
        "error_msg",
    )

    def __init__(self, *arg, **kwargs):
        """
        :param tuple arg: ignored
        :param dict kwargs: ignored
        """
        super(UserImportCsvResultExporter, self).__init__(*arg, **kwargs)
        self.factory = Factory()
        self.a_user = self.factory.make_import_user([])

    def get_iter(self, user_import):
        """
        Iterator over all ImportUsers and errors of the user import.
        First errors, then added, modified and deleted users.

        :param UserImport user_import: UserImport object used for the import
        :return: iterator over both ImportUsers and UcsSchoolImportError objects
        :rtype: Iterator(ImportUsers or UcsSchoolImportError)
        """

        def exc_count(exc):
            if exc.import_user:
                entry_count = exc.import_user.entry_count
            else:
                entry_count = 0
            return max(exc.entry_count, entry_count)

        li = sorted(user_import.errors, key=exc_count)
        for users in [user_import.added_users, user_import.modified_users, user_import.deleted_users]:
            tmp = list()
            map(tmp.extend, [u for u in users.values() if u])
            li.extend(tmp)
        li.sort(key=lambda x: int(x["entry_count"]) if isinstance(x, dict) else int(x.entry_count))
        return li

    def get_writer(self):
        """
        Object that will write the data to disk/network in the desired format.

        :return: an object that knows how to write data
        """
        return self.factory.make_user_writer(field_names=self.field_names)

    def serialize(self, obj):
        """
        Make a dict of attr_name->strings from an import object.

        :param obj: object to serialize
        :return: mapping attr_name->strings that will be used to write the output file
        :rtype: dict
        """
        from ..models.import_user import ImportUser

        is_error = False
        if isinstance(obj, ImportUser):
            user = obj
        elif isinstance(obj, UcsSchoolImportError):
            user = obj.import_user
            is_error = True
        elif isinstance(obj, dict):
            user = self.a_user.from_dict(obj)
        else:
            raise TypeError(
                "Expected ImportUser, UcsSchoolImportError or dict but got {}. Repr: {}".format(
                    type(obj), repr(obj)
                )
            )
        if not user:
            # error during reading of input data
            user = self.factory.make_import_user([role_pupil])  # set some role
            user.roles = []  # remove role

        return dict(
            line=getattr(user, "entry_count", 0),
            success=int(not is_error),
            error=int(is_error),
            action=user.action,
            role=user.role_string if user.roles else "",
            username=user.name,
            schools=" ".join(user.schools) if user.schools else user.school,
            firstname=user.firstname,
            lastname=user.lastname,
            birthday=user.birthday,
            email=user.email,
            disabled="0" if user.disabled == "0" else "1",
            classes=user.school_classes_as_str,
            source_uid=user.source_uid,
            record_uid=user.record_uid,
            error_msg=str(obj) if is_error else "",
        )
