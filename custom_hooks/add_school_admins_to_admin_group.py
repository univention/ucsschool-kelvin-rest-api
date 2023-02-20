# -*- coding: utf-8 -*-
#
# Copyright 2023 Univention GmbH
#
# https://www.univention.de/
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
# <https://www.gnu.org/licenses/>.
"""
Kelvin API Hook which adds the user to the group Admins of its school when the
user has the role `school_admin`.

To use it, copy it to
`/var/lib/ucs-school-import/kelvin-hooks/add_school_admins_to_admin_group.py`
"""

from ucsschool.importer.models.import_user import ImportUser
from ucsschool.importer.utils.user_pyhook import UserPyHook
from ucsschool.lib.roles import get_role_info
from ucsschool.lib.schoolldap import SchoolSearchBase
from univention.config_registry import ConfigRegistry

ucr = ConfigRegistry()
ucr.load()

ROLE = "school_admin"


class KelvinAddAdminGroupstoSchoolAdmins(UserPyHook):
    priority = {
        "post_create": 900,
    }

    async def post_create(self, obj: ImportUser) -> None:
        """
        Add school_admin users to the admin groups if necessary.
        :param: ImportUser.
        :return: None
        """
        self.logger.debug("Running a post_create hook for user %r" % obj.name)

        udm_obj = await obj.get_udm_object(self.udm)

        self.logger.info("User has groups %r" % udm_obj.props.groups)

        relevant_ucsschool_roles = [
            ucsschool_role
            for ucsschool_role in udm_obj.props.ucsschoolRole
            if get_role_info(ucsschool_role)[0] == ROLE and get_role_info(ucsschool_role)[1] == "school"
        ]
        added_groups = []

        for ucsschool_role in relevant_ucsschool_roles:
            target_group_dn: str = SchoolSearchBase([get_role_info(ucsschool_role)[2]]).admins_group
            if target_group_dn not in udm_obj.props.groups:
                udm_obj.props.groups.append(target_group_dn)
                added_groups.append(target_group_dn)
            else:
                self.logger.info("User %r already has %r" % (obj.name, target_group_dn))

        if added_groups:
            await udm_obj.save()
            self.logger.info("Added user %r to %r." % (obj.name, added_groups))
