# -*- coding: utf-8 -*-
#
# Univention UCS@school
#
# Copyright 2025 Univention GmbH
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

from typing import TYPE_CHECKING, Dict, Union  # noqa: F401

from fastapi import HTTPException, status

from ucsschool.lib.models.hook import Hook
from ucsschool.lib.models.user import User


class UserPreModValidationHook(Hook):
    model = User

    priority = {
        "pre_create": None,
        "post_create": None,
        "pre_modify": 999,
        "post_modify": None,
        "pre_move": 999,
        "post_move": None,
        "pre_remove": None,
        "post_remove": None,
    }  # type: Dict[str, Union[int, None]]

    async def pre_modify(self, user: "User") -> None:
        await self.error_on_validate(user)

    async def pre_move(self, user: "User") -> None:
        await self.error_on_validate(user)

    async def error_on_validate(self, user: "User") -> None:
        await user.validate(self.udm)
        udm_object = await user.get_udm_object(self.udm)
        dn_school = user.get_school_from_dn(user.dn)
        udm_obj_schools = udm_object.props.school
        if dn_school not in udm_obj_schools:
            user.add_error(
                "dn",
                f"Der Benutzer mit der DN='{user.dn}' befindet sich im LDAP Container der Schule='{dn_school}, "
                f"ist aber nicht Teil dieser Schule (siehe ucsschoolSchool attribut in UDM)'.",
            )
        if user.errors:
            self.logger.error(
                f"The UDM data of the user with DN={user.dn} is corrupted. Aborting operation.\n{user.errors}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"The UDM data of the user is corrupted. " f"Aborting operation.\n{user.errors}",
            )
