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
Kelvin API Hook which adds the user to the group Domain Admins when the user has
the ucsschoolRole: technical_admin:bsb:* (fachliche Leitstelle)
"""

from ucsschool.importer.models.import_user import ImportUser
from ucsschool.importer.utils.user_pyhook import UserPyHook
from univention.config_registry import ConfigRegistry

ucr = ConfigRegistry()
ucr.load()

ROLE = "school_admin"


class KelvinAddAdminGroupstoSchoolAdmins(UserPyHook):
    priority = {
        "post_create": 900,
    }

    @property
    def class_name(self):
        return type(self).__name__

    async def post_create(self, obj: ImportUser) -> None:
        """
        Get the user data after account creation
        to check the ucsschoolRole and add the
        user to the admin groups if necessary.
        :param: ImportUser.
        :return: None
        """
        self.logger.info("Running a post_create hook for user %r" % obj.name)

        target_group_dn: str = (
            f"cn={ucr.get('ucsschool/ldap/default/groupprefix/admins', 'admins-')}"
            f"{obj.school.lower()},cn=ouadmins,cn=groups,{ucr['ldap/base']}"
        )
        udm_obj = await obj.get_udm_object(self.udm)

        self.logger.info("User has groups %r" % udm_obj.props.groups)

        if (
            any(
                ur.split(":")[0] == ROLE and ur.split(":")[1] == "school"
                for ur in udm_obj.props.ucsschoolRole
            )
            and target_group_dn not in udm_obj.props.groups
        ):
            self.logger.info("Adding user %r to %r." % (obj.name, target_group_dn))
            udm_obj.props.groups.append(target_group_dn)
            await udm_obj.save()
        else:
            self.logger.info(
                "User %r doesn't have the role %r or already has %r" % (obj.name, ROLE, target_group_dn)
            )
        self.logger.info("Done!")
