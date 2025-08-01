# Copyright 2020-2021 Univention GmbH
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

from enum import Enum
from typing import List, Type
from urllib.parse import ParseResult, urlparse

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, HttpUrl

from ucsschool.importer.factory import Factory
from ucsschool.importer.models.import_user import ImportUser
from ucsschool.lib.roles import (
    UcsschoolRoleStringError,
    create_ucsschool_role_string,
    get_role_info,
    role_exam_user,
    role_school_admin,
    role_staff,
    role_student,
    role_teacher,
)

from ..import_config import init_ucs_school_import_framework
from ..ldap import LdapUser
from ..token_auth import get_kelvin_admin
from ..urls import cached_url_for

router = APIRouter()
_roles_to_class = {}


class SchoolUserRole(str, Enum):
    school_admin = "school_admin"
    staff = "staff"
    student = "student"
    teacher = "teacher"

    @classmethod
    def from_lib_role(cls, lib_role: str) -> "SchoolUserRole":
        try:
            role, _, _ = get_role_info(lib_role)
        except UcsschoolRoleStringError as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
        if role in (role_exam_user, role_student):
            return cls.student
        if role == role_teacher:
            return cls.teacher
        if role == role_staff:
            return cls.staff
        if role == role_school_admin:
            return cls.school_admin
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unknown UCS@school role {lib_role!r}.",
        )

    @classmethod
    def get_lib_class(cls, roles: List["SchoolUserRole"]) -> Type[ImportUser]:
        role_names = sorted(role.name for role in roles) if roles else []
        key = tuple(role_names)
        if key not in _roles_to_class:
            init_ucs_school_import_framework()
            factory = Factory()
            user: ImportUser = factory.make_import_user(role_names)
            _roles_to_class[key] = user.__class__
        return _roles_to_class[key]

    def as_lib_role(self, school: str) -> str:
        """
        Creates a list containing the role(s) in lib format.
        :param school: The school to create the role for.
        :return: The list containing the SchoolUserRole representation for
            consumation by the school lib.
        """
        if self.value == self.staff:
            return create_ucsschool_role_string(role_staff, school)
        elif self.value == self.student:
            return create_ucsschool_role_string(role_student, school)
        elif self.value == self.teacher:
            return create_ucsschool_role_string(role_teacher, school)
        elif self.value == self.school_admin:
            return create_ucsschool_role_string(role_school_admin, school)

    def to_url(self, request: Request) -> HttpUrl:
        url = cached_url_for(request, "get", role_name=self.value)
        up: ParseResult = urlparse(str(url))
        replaced = up._replace(scheme="https")
        return HttpUrl(replaced.geturl(), scheme="https", host=up.netloc)


class RoleModel(BaseModel):
    name: str
    display_name: str
    url: HttpUrl


@router.get("/", response_model=List[RoleModel])
async def search(
    request: Request, kelvin_admin: LdapUser = Depends(get_kelvin_admin)
) -> List[RoleModel]:
    """
    List all available roles.
    """
    return [
        RoleModel(name=role.name, display_name=role.name, url=role.to_url(request))
        for role in (
            SchoolUserRole.staff,
            SchoolUserRole.student,
            SchoolUserRole.teacher,
            SchoolUserRole.school_admin,
        )
    ]


@router.get("/{role_name}", response_model=RoleModel)
async def get(
    request: Request,
    role_name: str = Path(
        default=...,
        title="name",
    ),
    kelvin_admin: LdapUser = Depends(get_kelvin_admin),
) -> RoleModel:
    """Get a role by name.

    The name must be one of the following:
        - staff
        - student
        - teacher
    """
    try:
        role_name = SchoolUserRole(role_name)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No object with name={role_name!r} found or not authorized.",
        )

    return RoleModel(
        name=role_name,
        display_name=role_name,
        url=SchoolUserRole(role_name).to_url(request),
    )
