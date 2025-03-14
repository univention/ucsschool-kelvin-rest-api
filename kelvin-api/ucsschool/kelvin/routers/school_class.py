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

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, HttpUrl, root_validator, validator

from ucsschool.lib.models.attributes import ValidationError as LibValidationError
from ucsschool.lib.models.base import UDMPropertiesError
from ucsschool.lib.models.group import SchoolClass
from ucsschool.lib.schoolldap import name_from_dn
from udm_rest_client import UDM, CreateError, ModifyError

from ..config import UDM_MAPPING_CONFIG
from ..ldap import LdapUser
from ..token_auth import get_kelvin_admin
from ..urls import cached_url_for, url_to_dn, url_to_name
from .base import (
    APIAttributesMixin,
    UcsSchoolBaseModel,
    get_lib_obj,
    get_logger,
    only_known_udm_properties,
    udm_ctx,
)
from .school import search_schools_in_ldap

router = APIRouter()


def check_name(value: str) -> str:
    """
    The SchoolClass.name is checked in check_name2.
    This function is reused as a pass-through validator,
    root_validator can't be reused this way.
    """
    return value


class SchoolClassCreateModel(UcsSchoolBaseModel):
    description: str = None
    users: List[HttpUrl] = None
    create_share: bool = True

    class Config(UcsSchoolBaseModel.Config):
        lib_class = SchoolClass
        config_id = "school_class"

    _validate_name = validator("name", allow_reuse=True)(check_name)

    @root_validator(skip_on_failure=True)
    def check_name2(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate 'OU-name' to prevent 'must be at least 2 characters long'
        error when checking a class name with just one char.
        """
        school = values["school"].split("/")[-1]
        class_name = f"{school}-{values['name']}"
        cls.Config.lib_class.name.validate(class_name)
        return values

    @classmethod
    async def _from_lib_model_kwargs(
        cls, obj: SchoolClass, request: Request, udm: UDM
    ) -> Dict[str, Any]:
        kwargs = await super()._from_lib_model_kwargs(obj, request, udm)
        kwargs["url"] = cls.scheme_and_quote(
            str(cached_url_for(request, "get", class_name=kwargs["name"], school=obj.school))
        )
        kwargs["users"] = [
            cls.scheme_and_quote(str(cached_url_for(request, "get", username=name_from_dn(dn))))
            for dn in obj.users
        ]
        return kwargs

    def _as_lib_model_kwargs(self, request: Request) -> Dict[str, Any]:
        kwargs = super()._as_lib_model_kwargs(request)
        school_name = url_to_name(request, "school", self.unscheme_and_unquote(kwargs["school"]))
        kwargs["name"] = f"{school_name}-{self.name}"
        kwargs["users"] = [
            url_to_dn(request, "user", self.unscheme_and_unquote(user)) for user in (self.users or [])
        ]  # this is expensive :/
        return kwargs


class SchoolClassModel(SchoolClassCreateModel, APIAttributesMixin):
    pass


class SchoolClassPatchDocument(BaseModel):
    name: str = None
    description: str = None
    ucsschool_roles: List[str] = Field(None, title="Roles of this object. Don't change if unsure.")
    users: List[HttpUrl] = None
    udm_properties: Dict[str, Any] = None

    class Config(UcsSchoolBaseModel.Config):
        lib_class = SchoolClass

    @validator("name")
    def check_name(cls, value: str) -> str:
        """
        At this point we know `school` is valid, but
        we don't have it in the values. Thus we use
        the dummy school name DEMOSCHOOL.
        """
        class_name = f"DEMOSCHOOL-{value}"
        cls.Config.lib_class.name.validate(class_name)
        return value

    @validator("udm_properties")
    def only_known_udm_properties(cls, udm_properties: Optional[Dict[str, Any]]):
        configured_properties = set(UDM_MAPPING_CONFIG.school_class or [])
        return only_known_udm_properties(
            udm_properties, configured_properties, SchoolClassCreateModel.Config.config_id
        )

    async def to_modify_kwargs(self, school, request: Request) -> Dict[str, Any]:
        res = self.dict(exclude_unset=True)
        if "name" in res:
            res["name"] = f"{school}-{self.name}"

        logger = get_logger()

        if "users" in res:
            if res["users"] is None:
                logger.warning(
                    "Setting the users attribute to None is deprecated."
                    " None is ignored and will not delete users from the school class."
                )
                del res["users"]
            else:
                res["users"] = [
                    url_to_dn(request, "user", UcsSchoolBaseModel.unscheme_and_unquote(user))
                    for user in (self.users or [])
                ]  # this is expensive :/
        return res


@router.get("/", response_model=List[SchoolClassModel])
async def search(
    request: Request,
    school: str = Query(
        ...,
        description="Name of school (``OU``) in which to search for classes "
        "(**case sensitive, exact match, required**).",
        min_length=2,
    ),
    class_name: str = Query(
        None,
        alias="name",
        description="List classes with this name. (optional, ``*`` can be used "
        "for an inexact search).",
        title="name",
    ),
    udm: UDM = Depends(udm_ctx),
    kelvin_admin: LdapUser = Depends(get_kelvin_admin),
) -> List[SchoolClassModel]:
    """
    Search for school classes.

    - **school**: school (``OU``) the classes belong to, **case sensitive**,
        exact match only (required)
    - **name**: names of school classes to look for, use ``*`` for inexact
        search (optional)
    """
    if class_name:
        filter_str = f"name={school}-{class_name}"
    else:
        filter_str = None

    scs = await SchoolClass.get_all(udm, school, filter_str)
    return [await SchoolClassModel.from_lib_model(sc, request, udm) for sc in scs]


@router.get("/{school}/{class_name}", response_model=SchoolClassModel)
async def get(
    class_name: str,
    school: str,
    request: Request,
    udm: UDM = Depends(udm_ctx),
    kelvin_admin: LdapUser = Depends(get_kelvin_admin),
) -> SchoolClassModel:
    sc = await get_lib_obj(udm, SchoolClass, f"{school}-{class_name}", school)
    return await SchoolClassModel.from_lib_model(sc, request, udm)


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=SchoolClassModel)
async def create(
    school_class: SchoolClassCreateModel,
    request: Request,
    udm: UDM = Depends(udm_ctx),
    logger: logging.Logger = Depends(get_logger),
    kelvin_admin: LdapUser = Depends(get_kelvin_admin),
) -> SchoolClassModel:
    """
    Create a **school class** with all the information:

    **Request Body**

    - **name**: name of the school class (**required**)
    - **school**: **URL** of the school resource the class belongs to (**required**)
        **ATTENTION: Once created, the school cannot be changed!**
    - **description**: additional text (optional)
    - **users**: list of **URLs** of User resources (optional)
    - **create_share**: whether a share should be created for the class
        (optional)
    - **ucsschool_roles**: list of tags of the form
        $ROLE:$CONTEXT_TYPE:$CONTEXT (optional)
    - **udm_properties**: object with UDM properties (optional, e.g.
        **{"udm_prop1": "value1"}**, must be configured in
        **mapped_udm_properties**, see documentation)

    **JSON Example:**

        {
            "udm_properties": {},
            "name": "EXAMPLE_CLASS",
            "school": "http://<fqdn>/ucsschool/kelvin/v1/schools/EXAMPLE_SCHOOL",
            "description": "Example description",
            "create_share": false,
            "users": [
                "http://<fqdn>/ucsschool/kelvin/v1/users/EXAMPLE_STUDENT"
            ]
        }
    """
    sc: SchoolClass = school_class.as_lib_model(request)
    ou_names = await search_schools_in_ldap(sc.school, raise404=True)
    sc.school = ou_names[0]  # use OU name from LDAP, not from request (Bug #55456)
    sc.name = f"{sc.school}-{school_class.name}"
    if await sc.exists(udm):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="School class exists.")
    try:
        await sc.create(udm)
    except (LibValidationError, CreateError, UDMPropertiesError) as exc:
        error_msg = f"Failed to create school class {sc!r}: {exc}"
        logger.exception(error_msg)
        if isinstance(exc, CreateError):
            raise
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)
    return await SchoolClassModel.from_lib_model(sc, request, udm)


@router.patch(
    "/{school}/{class_name}",
    status_code=status.HTTP_200_OK,
    response_model=SchoolClassModel,
)
async def partial_update(
    class_name: str,
    school: str,
    school_class: SchoolClassPatchDocument,
    request: Request,
    udm: UDM = Depends(udm_ctx),
    logger: logging.Logger = Depends(get_logger),
    kelvin_admin: LdapUser = Depends(get_kelvin_admin),
) -> SchoolClassModel:
    """
    Update a **school class** with all the information:

    **Parameters**

    - **class_name**: current name of the class , if the name changes within the
        body this parameter will change accordingly (**required**)
    - **school**: name of the school the queried class is assigned to (**required**)

    **Request Body**

    All attributes are **optional**

    - **name**: name of the school class
    - **description**: additional text
    - **users**: list of URLs to User resources
    - **ucsschool_roles**: list of tags of the form
        $ROLE:$CONTEXT_TYPE:$CONTEXT
    - **udm_properties**: object with UDM properties (e.g.
        **{"udm_prop1": "value1"}**, must be configured in
        **mapped_udm_properties**, see documentation)

    **JSON Example:**

        {
            "description": "Changed example description"
        }
    """
    ou_names = await search_schools_in_ldap(school, raise404=True)
    school = ou_names[0]  # use OU name from LDAP, not from request (Bug #55456)
    sc_current = await get_lib_obj(udm, SchoolClass, f"{school}-{class_name}", school)
    changed = False
    for attr, new_value in (await school_class.to_modify_kwargs(school, request)).items():
        current_value = getattr(sc_current, attr)
        if new_value != current_value:
            setattr(sc_current, attr, new_value)
            changed = True
    if changed:
        try:
            await sc_current.modify(udm)
        except (LibValidationError, ModifyError, UDMPropertiesError) as exc:
            logger.warning(
                "Error modifying school class %r with %r: %s",
                sc_current,
                await request.json(),
                exc,
            )
            if isinstance(exc, ModifyError):
                raise
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
    return await SchoolClassModel.from_lib_model(sc_current, request, udm)


@router.put(
    "/{school}/{class_name}",
    status_code=status.HTTP_200_OK,
    response_model=SchoolClassModel,
)
async def complete_update(
    class_name: str,
    school: str,
    school_class: SchoolClassCreateModel,
    request: Request,
    udm: UDM = Depends(udm_ctx),
    logger: logging.Logger = Depends(get_logger),
    kelvin_admin: LdapUser = Depends(get_kelvin_admin),
) -> SchoolClassModel:
    """
    Update a **school class** with all the information:

    **Parameters**

    - **class_name**: current name of the class , if the name changes within the body
        this parameter will change accordingly (**required**)
    - **school**: name of the school the queried class is assigned to (**required**)

    **Request Body**

    - **name**: name of the school class (**required**)
    - **school**: school the class belongs to (**required**)
        **ATTENTION: The original school (set on creation) cannot be changed!**
    - **description**: additional text (optional)
    - **users**: list of URLs to User resources (optional)
    - **ucsschool_roles**: list of tags of the form
        $ROLE:$CONTEXT_TYPE:$CONTEXT (optional)
    - **udm_properties**: object with UDM properties (optional, e.g.
        **{"udm_prop1": "value1"}**, must be configured in
        **mapped_udm_properties**, see documentation)

    **JSON Example:**

        {
            "udm_properties": {},
            "name": "EXAMPLE_CLASS",
            "school": "http://<fqdn>/ucsschool/kelvin/v1/schools/EXAMPLE_SCHOOL",
            "description": "Example description",
            "users": [
                "http://<fqdn>/ucsschool/kelvin/v1/users/EXAMPLE_STUDENT"
            ]
        }
    """
    ou_names = await search_schools_in_ldap(school, raise404=True)
    school = ou_names[0]  # use OU name from LDAP, not from request (Bug #55456)
    school_class_school = url_to_name(
        request, "school", UcsSchoolBaseModel.unscheme_and_unquote(school_class.school)
    )
    if school.lower() != school_class_school.lower():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Moving of class to other school is not allowed.",
        )
    sc_current = await get_lib_obj(udm, SchoolClass, f"{school}-{class_name}", school)
    changed = False
    sc_request: SchoolClass = school_class.as_lib_model(request)
    sc_request.school = school
    sc_request.name = f"{school}-{school_class.name}"
    sc_current.udm_properties = sc_request.udm_properties
    for attr in SchoolClass._attributes.keys():
        current_value = getattr(sc_current, attr)
        new_value = getattr(sc_request, attr)
        if attr in ("ucsschool_roles", "users") and new_value is None:
            new_value = []
        if new_value != current_value:
            setattr(sc_current, attr, new_value)
            changed = True
    if changed or sc_current.udm_properties:
        try:
            await sc_current.modify(udm)
        except (LibValidationError, ModifyError, UDMPropertiesError) as exc:
            logger.warning(
                "Error modifying school class %r with %r: %s",
                sc_current,
                await request.json(),
                exc,
            )
            if isinstance(exc, ModifyError):
                raise
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
    return await SchoolClassModel.from_lib_model(sc_current, request, udm)


@router.delete("/{school}/{class_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    class_name: str,
    school: str,
    request: Request,
    udm: UDM = Depends(udm_ctx),
    kelvin_admin: LdapUser = Depends(get_kelvin_admin),
) -> Response:
    sc = await get_lib_obj(udm, SchoolClass, f"{school}-{class_name}", school)
    await sc.remove(udm)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
