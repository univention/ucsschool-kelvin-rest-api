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
from ucsschool.lib.models.group import WorkGroup
from udm_rest_client import UDM, CreateError, ModifyError

from ..config import UDM_MAPPING_CONFIG
from ..opa import OPAClient
from ..token_auth import get_token
from ..urls import name_from_dn, url_to_dn, url_to_name
from .base import APIAttributesMixin, UcsSchoolBaseModel, get_lib_obj, get_logger, udm_ctx

router = APIRouter()


def check_name(value: str) -> str:
    """
    The WorkGroup.name is checked in check_name2.
    This function is reused as a pass-through validator,
    root_validator can't be reused this way.
    """
    return value


class WorkGroupCreateModel(UcsSchoolBaseModel):
    description: str = None
    users: List[HttpUrl] = None
    create_share: bool = True
    email: str = None
    allowed_email_senders_users: List[str] = []
    allowed_email_senders_groups: List[str] = []

    class Config(UcsSchoolBaseModel.Config):
        lib_class = WorkGroup
        config_id = "workgroup"

    _validate_name = validator("name", allow_reuse=True)(check_name)

    @root_validator
    def check_name2(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate 'OU-name' to prevent 'must be at least 2 characters long'
        error when checking a workgroup name with just one char.
        """
        school = values.get("school", "").split("/")[-1]
        workgroup_name = f"{school}-{values['name']}"
        cls.Config.lib_class.name.validate(workgroup_name)
        return values

    @classmethod
    async def _from_lib_model_kwargs(cls, obj: WorkGroup, request: Request, udm: UDM) -> Dict[str, Any]:
        kwargs = await super()._from_lib_model_kwargs(obj, request, udm)
        kwargs["url"] = cls.scheme_and_quote(
            request.url_for("get", workgroup_name=kwargs["name"], school=obj.school)
        )
        kwargs["users"] = [
            cls.scheme_and_quote(request.url_for("get", username=name_from_dn(dn))) for dn in obj.users
        ]
        return kwargs

    async def _as_lib_model_kwargs(self, request: Request) -> Dict[str, Any]:
        kwargs = await super()._as_lib_model_kwargs(request)
        school_name = url_to_name(request, "school", self.unscheme_and_unquote(kwargs["school"]))
        kwargs["name"] = f"{school_name}-{self.name}"
        kwargs["users"] = [
            await url_to_dn(request, "user", self.unscheme_and_unquote(user))
            for user in (self.users or [])
        ]  # this is expensive :/
        return kwargs


class WorkGroupModel(WorkGroupCreateModel, APIAttributesMixin):
    pass


class WorkGroupPatchDocument(BaseModel):
    school: str = None
    name: str = None
    description: str = None
    ucsschool_roles: List[str] = Field(None, title="Roles of this object. Don't change if unsure.")
    users: List[HttpUrl] = None
    udm_properties: Dict[str, Any] = None

    class Config(UcsSchoolBaseModel.Config):
        lib_class = WorkGroup

    @validator("name")
    def check_name(cls, value: str) -> str:
        """
        At this point we know `school` is valid, but
        we don't have it in the values. Thus we use
        the dummy school name DEMOSCHOOL.
        """
        workgroup_name = f"DEMOSCHOOL-{value}"
        cls.Config.lib_class.name.validate(workgroup_name)
        return value

    @validator("udm_properties")
    def only_known_udm_properties(cls, udm_properties: Optional[Dict[str, Any]]):
        property_list = getattr(UDM_MAPPING_CONFIG, "workgroup", [])
        if not udm_properties:
            return udm_properties
        for key in udm_properties:
            if key not in property_list:
                raise ValueError(
                    f"The udm property {key!r} was not configured for this resource "
                    f"and thus is not allowed."
                )
        return udm_properties

    async def to_modify_kwargs(self, school, request: Request) -> Dict[str, Any]:
        res = {}
        if self.school:
            res["school"] = self.school
        if self.name:
            res["name"] = f"{school}-{self.name}"
        if self.description:
            res["description"] = self.description
        if self.ucsschool_roles:
            res["ucsschool_roles"] = self.ucsschool_roles
        if self.udm_properties:
            res["udm_properties"] = self.udm_properties
        if self.users:
            res["users"] = [
                await url_to_dn(request, "user", UcsSchoolBaseModel.unscheme_and_unquote(user))
                for user in (self.users or [])
            ]  # this is expensive :/
        return res


@router.get("/", response_model=List[WorkGroupModel])
async def search(
    request: Request,
    school: str = Query(
        ...,
        description="Name of school (``OU``) in which to search for workgroups "
        "(**case sensitive, exact match, required**).",
        min_length=2,
    ),
    workgroup_name: str = Query(
        None,
        alias="name",
        description="List workgroups with this name. (optional, ``*`` can be used "
        "for an inexact search).",
        title="name",
    ),
    udm: UDM = Depends(udm_ctx),
    token: str = Depends(get_token),
) -> List[WorkGroupModel]:
    """
    Search for school workgroups.

    - **school**: school (``OU``) the workgroups belong to, **case sensitive**,
        exact match only (required)
    - **name**: names of school workgroups to look for, use ``*`` for inexact
        search (optional)
    """
    if not await OPAClient.instance().check_policy_true(
        policy="workgroups",
        token=token,
        request=dict(method="GET", path=["workgroups"]),
        target={},
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorized to list school workgroups.",
        )
    if workgroup_name:
        filter_str = f"name={school}-{workgroup_name}"
    else:
        filter_str = None
    scs = await WorkGroup.get_all(udm, school, filter_str)
    return [await WorkGroupModel.from_lib_model(sc, request, udm) for sc in scs]


@router.get("/{school}/{workgroup_name}", response_model=WorkGroupModel)
async def get(
    workgroup_name: str,
    school: str,
    request: Request,
    udm: UDM = Depends(udm_ctx),
    token: str = Depends(get_token),
) -> WorkGroupModel:
    if not await OPAClient.instance().check_policy_true(
        policy="workgroups",
        token=token,
        request=dict(method="GET", path=["workgroups", workgroup_name]),
        target={},
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorized to list school workgroups.",
        )
    sc = await get_lib_obj(udm, WorkGroup, f"{school}-{workgroup_name}", school)
    return await WorkGroupModel.from_lib_model(sc, request, udm)


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=WorkGroupModel)
async def create(
    workgroup: WorkGroupCreateModel,
    request: Request,
    udm: UDM = Depends(udm_ctx),
    logger: logging.Logger = Depends(get_logger),
    token: str = Depends(get_token),
) -> WorkGroupModel:
    """
    Create a **workgroup** with all the information:

    **Request body**

    - **name**: name of the school workgroup (**required**)
    - **school**: **URL** of the school the workgroup belongs to (**required**)
        **ATTENTION: Once created, the school cannot be changed!**
    - **description**: additional text (optional)
    - **users**: list of **URLs** of User resources (optional)
    - **create_share**: whether a share should be created for the workgroup
        (optional)
    - **email**: workgroup's email (optional)
    - **allowed_email_senders_users**: users that are allowed to send e-mails
        to the workgroup (optional)
    - **allowed_email_senders_groups**: groups that are allowed to send e-mails
        to the workgroup (optional)
    - **ucsschool_roles**: list of tags of the form
        $ROLE:$CONTEXT_TYPE:$CONTEXT (optional)
    - **udm_properties**: object with UDM properties (optional, e.g.
        **{"udm_prop1": "value1"}**, must be configured in
        **mapped_udm_properties**, see documentation)

    **JSON Example:**

        {
            "udm_properties": {},
            "name": "EXAMPLE_WORKGROUP",
            "school": "http://<fqdn>/ucsschool/kelvin/v1/schools/EXAMPLE_SCHOOL",
            "description": "Example description",
            "users": [
                "http://<fqdn>/ucsschool/kelvin/v1/users/EXAMPLE_STUDENT"
            ],
            "email": null,
            "allowed_email_senders_users": [],
            "allowed_email_senders_groups": []
        }
    """
    if not await OPAClient.instance().check_policy_true(
        policy="workgroups",
        token=token,
        request=dict(method="POST", path=["workgroups"]),
        target={},
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorized to create school workgroups.",
        )
    sc: WorkGroup = await workgroup.as_lib_model(request)
    if await sc.exists(udm):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="school workgroup exists.")
    else:
        try:
            await sc.create(udm)
        except (LibValidationError, CreateError, UDMPropertiesError) as exc:
            error_msg = f"Failed to create school workgroup {sc!r}: {exc}"
            logger.exception(error_msg)
            if isinstance(exc, CreateError):
                raise
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)
    return await WorkGroupModel.from_lib_model(sc, request, udm)


def _validate_change(attr):
    if attr == "school":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Moving a workgroup to another school is not allowed.",
        )


@router.patch(
    "/{school}/{workgroup_name}",
    status_code=status.HTTP_200_OK,
    response_model=WorkGroupModel,
)
async def partial_update(
    workgroup_name: str,
    school: str,
    workgroup: WorkGroupPatchDocument,
    request: Request,
    udm: UDM = Depends(udm_ctx),
    logger: logging.Logger = Depends(get_logger),
    token: str = Depends(get_token),
) -> WorkGroupModel:
    """
    Update a **workgroup** with all the information:

    **Parameters**

    - **workgroup_name**: current name of the workgroup , if the name changes within the
        body this parameter will change accordingly (**required**)
    - **school**: name of the school the queried workgroup is assigned to (**required**)

    **Request Body**

    - **name**: name of the school workgroup (**required**)
    - **school**: **URL** of the school the workgroup belongs to (**required**)
        **ATTENTION: Once created, the school cannot be changed!**
    - **description**: additional text (optional)
    - **users**: list of **URLs** of User resources (optional)
    - **create_share**: whether a share should be created for the workgroup
        (optional)
    - **email**: workgroup's email (optional)
    - **allowed_email_senders_users**: users that are allowed to send e-mails
        to the workgroup (optional)
    - **allowed_email_senders_groups**: groups that are allowed to send e-mails
        to the workgroup (optional)
    - **ucsschool_roles**: list of tags of the form
        $ROLE:$CONTEXT_TYPE:$CONTEXT (optional)
    - **udm_properties**: object with UDM properties (optional, e.g.
        **{"udm_prop1": "value1"}**, must be configured in
        **mapped_udm_properties**, see documentation)

    **JSON Example:**

        {
            "udm_properties": {},
            "name": "EXAMPLE_WORKGROUP",
            "school": "http://<fqdn>/ucsschool/kelvin/v1/schools/EXAMPLE_SCHOOL",
            "description": "Example description",
            "users": [
                "http://<fqdn>/ucsschool/kelvin/v1/users/EXAMPLE_STUDENT"
            ],
            "email": null,
            "allowed_email_senders_users": [],
            "allowed_email_senders_groups": []
        }
    """
    if not await OPAClient.instance().check_policy_true(
        policy="workgroups",
        token=token,
        request=dict(method="PATCH", path=["workgroups", workgroup_name]),
        target={},
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorized to edit school workgroups.",
        )
    sc_current = await get_lib_obj(udm, WorkGroup, f"{school}-{workgroup_name}", school)
    changed = False
    for attr, new_value in (await workgroup.to_modify_kwargs(school, request)).items():
        current_value = getattr(sc_current, attr)
        if new_value != current_value:
            _validate_change(attr)
            setattr(sc_current, attr, new_value)
            changed = True
    if changed:
        try:
            await sc_current.modify(udm)
        except (LibValidationError, ModifyError, UDMPropertiesError) as exc:
            logger.warning(
                "Error modifying school workgroup %r with %r: %s",
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
    return await WorkGroupModel.from_lib_model(sc_current, request, udm)


@router.put(
    "/{school}/{workgroup_name}",
    status_code=status.HTTP_200_OK,
    response_model=WorkGroupModel,
)
async def complete_update(
    workgroup_name: str,
    school: str,
    workgroup: WorkGroupCreateModel,
    request: Request,
    udm: UDM = Depends(udm_ctx),
    logger: logging.Logger = Depends(get_logger),
    token: str = Depends(get_token),
) -> WorkGroupModel:
    """
    Update a **workgroup** with all the information:

    **Parameters**

    - **workgroup_name**: current name of the workgroup , if the name changes within the
        body this parameter will change accordingly (**required**)
    - **school**: name of the school the queried workgroup is assigned to (**required**)

    **Request Body**

    - **name**: name of the school workgroup (**required**)
    - **school**: **URL** of the school the workgroup belongs to (**required**)
        **ATTENTION: Once created, the school cannot be changed!**
    - **description**: additional text (optional)
    - **users**: list of **URLs** of User resources (optional)
    - **create_share**: whether a share should be created for the workgroup
        (optional)
    - **email**: workgroup's email (optional)
    - **allowed_email_senders_users**: users that are allowed to send e-mails
        to the workgroup (optional)
    - **allowed_email_senders_groups**: groups that are allowed to send e-mails
        to the workgroup (optional)
    - **ucsschool_roles**: list of tags of the form
        $ROLE:$CONTEXT_TYPE:$CONTEXT (optional)
    - **udm_properties**: object with UDM properties (optional, e.g.
        **{"udm_prop1": "value1"}**, must be configured in
        **mapped_udm_properties**, see documentation)

    **JSON Example:**

        {
            "udm_properties": {},
            "name": "EXAMPLE_WORKGROUP",
            "school": "http://<fqdn>/ucsschool/kelvin/v1/schools/EXAMPLE_SCHOOL",
            "description": "Example description",
            "users": [
                "http://<fqdn>/ucsschool/kelvin/v1/users/EXAMPLE_STUDENT"
            ],
            "email": null,
            "allowed_email_senders_users": [],
            "allowed_email_senders_groups": []
        }
    """
    if not await OPAClient.instance().check_policy_true(
        policy="workgroups",
        token=token,
        request=dict(method="PUT", path=["workgroups", workgroup_name]),
        target={},
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorized to edit school workgroups.",
        )
    if school != url_to_name(
        request, "school", UcsSchoolBaseModel.unscheme_and_unquote(workgroup.school)
    ):
        _validate_change("school")
    sc_current = await get_lib_obj(udm, WorkGroup, f"{school}-{workgroup_name}", school)
    changed = False
    sc_request: WorkGroup = await workgroup.as_lib_model(request)
    sc_current.udm_properties = sc_request.udm_properties
    for attr in WorkGroup._attributes.keys():
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
                "Error modifying school workgroup %r with %r: %s",
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
    return await WorkGroupModel.from_lib_model(sc_current, request, udm)


@router.delete("/{school}/{workgroup_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    workgroup_name: str,
    school: str,
    request: Request,
    udm: UDM = Depends(udm_ctx),
    token: str = Depends(get_token),
) -> Response:
    if not await OPAClient.instance().check_policy_true(
        policy="workgroups",
        token=token,
        request=dict(method="DELETE", path=["workgroups", workgroup_name]),
        target={},
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorized to delete school workgroups.",
        )
    sc = await get_lib_obj(udm, WorkGroup, f"{school}-{workgroup_name}", school)
    await sc.remove(udm)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
