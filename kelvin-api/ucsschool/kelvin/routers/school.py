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
from functools import lru_cache
from typing import Any, Dict, List, Optional

from aiocache import Cache, cached
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    status,
)
from ldap.filter import escape_filter_chars, filter_format
from pydantic import validator
from uldap3.exceptions import NoObject

from ucsschool.importer.models.import_user import ImportUser
from ucsschool.lib.create_ou import create_ou
from ucsschool.lib.models.computer import AnyComputer, SchoolDCSlave
from ucsschool.lib.models.school import School
from ucsschool.lib.models.utils import env_or_ucr
from ucsschool.lib.schoolldap import name_from_dn
from udm_rest_client import UDM

from ...lib.models.base import UDMPropertiesError
from ..ldap import LdapUser, uldap_admin_read_local
from ..token_auth import get_kelvin_admin
from ..urls import cached_url_for
from .base import APIAttributesMixin, LibModelHelperMixin, udm_ctx

router = APIRouter()

OU_CACHE_NAMESPACE = __name__
OU_CACHE_TTL = int(env_or_ucr("ucsschool/kelvin/cache_ttl") or "300")


@lru_cache(maxsize=1)
def get_logger() -> logging.Logger:
    return logging.getLogger(__name__)


def ou_cache_key(func, *args, **kwargs):
    return (
        f"{func.__name__}+"
        f"{'-'.join(repr(a) for a in args)}+"
        f"{'-'.join(f'{k!r}={v!r}' for k, v in kwargs.items())}"
    )


class SchoolCreateModel(LibModelHelperMixin):
    # not subclassing 'UcsSchoolBaseModel' because that has a 'school' attribute
    name: str
    display_name: str = None
    educational_servers: List[str] = []
    administrative_servers: List[str] = []
    class_share_file_server: str = None
    home_share_file_server: str = None

    class Config(LibModelHelperMixin.Config):
        lib_class = School
        config_id = "school"

    @validator("name", check_fields=False)
    def check_name(cls, value: str) -> str:
        cls.Config.lib_class.name.validate(value)
        return value


class SchoolModel(SchoolCreateModel, APIAttributesMixin):
    class Config(SchoolCreateModel.Config):
        ...

    @classmethod
    async def _from_lib_model_kwargs(cls, obj: School, request: Request, udm: UDM) -> Dict[str, Any]:
        kwargs = await super()._from_lib_model_kwargs(obj, request, udm)
        kwargs["url"] = cls.scheme_and_quote(
            str(cached_url_for(request, "school_get", school_name=kwargs["name"]))
        )
        kwargs["administrative_servers"] = [
            name for name in [computer_dn2name(dn) for dn in obj.administrative_servers] if name
        ]
        kwargs["class_share_file_server"] = computer_dn2name(obj.class_share_file_server)
        kwargs["educational_servers"] = [
            name for name in [computer_dn2name(dn) for dn in obj.educational_servers] if name
        ]
        kwargs["home_share_file_server"] = computer_dn2name(obj.home_share_file_server)
        return kwargs


def computer_dn2name(dn: str) -> Optional[str]:
    if not dn:
        return None
    uldap = uldap_admin_read_local()
    filter_s, base = dn.split(",", 1)
    filter_s = f"({filter_s})"
    try:
        for entry in uldap.search(search_filter=filter_s, search_base=base, attributes=["cn"]):
            return entry["cn"].value
    except NoObject:
        pass
    return None


@lru_cache(maxsize=1024)
def computer_name2dn(name: str) -> Optional[str]:
    uldap = uldap_admin_read_local()
    for dn in uldap.search_dn(School._ldap_filter(name)):
        return dn
    return None


async def fix_school_attributes(
    school_obj: School, school: SchoolCreateModel, logger: logging.Logger, udm: UDM
):
    """
    Fix attributes of `school_obj` according to `school`, as `create_ou()` does not support multiple DCs.

    Side effect: changes attributes of `school_obj` and saves it to LDAP.
    """
    # We have to assume the school object also changed if there are udm properties set
    changed = False or bool(school_obj.udm_properties)
    if len(school_obj.administrative_servers) != len(school.administrative_servers):
        dns = []
        for host in school.administrative_servers:
            if dn := computer_name2dn(host):
                dns.append(dn)
            else:
                success = await school_obj.create_dc_slave(udm, host, True)
                if success:
                    dns.append(SchoolDCSlave(name=host, school=school_obj.name).dn)
                else:
                    logger.error("Error creating administrativ DC %r for OU %r.", host, school_obj.name)
        school_obj.administrative_servers = dns
        changed = True
    if school.educational_servers and len(school_obj.educational_servers) != len(
        school.educational_servers
    ):
        dns = []
        for host in school.educational_servers:
            if dn := computer_name2dn(host):
                dns.append(dn)
            else:
                success = await school_obj.create_dc_slave(udm, host, False)
                if success:
                    dns.append(SchoolDCSlave(name=host, school=school_obj.name).dn)
                else:
                    logger.error("Error creating educational DC %r for OU %r.", host, school_obj.name)
        school_obj.educational_servers = dns
        changed = True
    if (
        school.class_share_file_server
        and name_from_dn(school_obj.class_share_file_server) != school.class_share_file_server
    ):
        school_obj.class_share_file_server = computer_name2dn(school.class_share_file_server)
        changed = True
    if (
        school.home_share_file_server
        and name_from_dn(school_obj.home_share_file_server) != school.home_share_file_server
    ):
        school_obj.home_share_file_server = computer_name2dn(school.home_share_file_server)
        changed = True
    if changed:
        await school_obj.modify(udm)
    else:
        logger.debug("Nothing to do.")


async def validate_create_request_params(school: SchoolCreateModel, logger: logging.Logger, udm: UDM):
    for attr_name in ("administrative_servers", "educational_servers"):
        servers = getattr(school, attr_name)
        if servers and len(servers) > 1:
            error_msg = f"More than one host in parameter {attr_name!r} is not supported."
            logger.error(error_msg)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error_msg)
    for share_attr_name in ("class_share_file_server", "home_share_file_server"):
        share_host = getattr(school, share_attr_name)
        if share_host:
            # must either exist or must be automatically created by create_ou()
            if (
                not await AnyComputer(name=share_host).exists(udm)
                and share_host != f"dc{school.name}"
                and share_host not in school.administrative_servers
                and share_host not in school.educational_servers
            ):
                error_msg = (
                    f"Host {share_host!r} in parameter {share_attr_name!r} does not exist and will not "
                    f"be automatically created. Supply the name of an existing host or one from "
                    f"'administrative_servers' or 'educational_servers' (or none to automatically use "
                    f"the educational server)."
                )
                logger.error(error_msg)
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error_msg)


@router.get("/", response_model=List[SchoolModel])
async def school_search(
    request: Request,
    name_filter: str = Query(
        None,
        alias="name",
        description="List schools with this name. '*' can be used for an " "inexact search. (optional)",
        title="name",
    ),
    logger: logging.Logger = Depends(get_logger),
    udm: UDM = Depends(udm_ctx),
    kelvin_admin: LdapUser = Depends(get_kelvin_admin),
) -> List[SchoolModel]:
    """
    Search for schools (OUs).

    The **name** parameter is optional and supports the use of ``*`` for wildcard
    searches. No other properties can be used to filter.
    """
    logger.debug("Searching for schools with: name_filter=%r", name_filter)
    if name_filter:
        filter_str = "ou={}".format(escape_filter_chars(name_filter).replace(r"\2a", "*"))
    else:
        filter_str = None
    schools = await School.get_all(udm, filter_str=filter_str)
    return [await SchoolModel.from_lib_model(school, request, udm) for school in schools]


@router.get("/{school_name}", response_model=SchoolModel)
async def school_get(
    request: Request,
    school_name: str = Path(
        default=...,
        description="School (OU) with this name.",
        title="name",
    ),
    udm: UDM = Depends(udm_ctx),
    kelvin_admin: LdapUser = Depends(get_kelvin_admin),
) -> SchoolModel:
    """
    Fetch a specific school (OU).

    - **name**: name of the school (**required**)
    """
    await search_schools_in_ldap(school_name, raise404=True)  # shortcut for case OU doesn't exist
    school = await School.from_dn(School(name=school_name).dn, None, udm)
    return await SchoolModel.from_lib_model(school, request, udm)


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=SchoolModel)
async def school_create(
    school: SchoolCreateModel,
    request: Request,
    background_tasks: BackgroundTasks,
    alter_dhcpd_base: Optional[bool] = None,
    udm: UDM = Depends(udm_ctx),
    logger: logging.Logger = Depends(get_logger),
    kelvin_admin: LdapUser = Depends(get_kelvin_admin),
) -> SchoolModel:
    """
    Create a school (OU) with all the information:

    **Parameters**

    - **alter_dhcpd_base**: whether the UCR variable dhcpd/ldap/base should be modified during school
        creation on singleserver environments. (optional, **currently non-functional!**)

    **Request Body**

    - **name**: name of the school class (**required**, only ASCII letters, digits and dashes are
        allowed, dash not at start or end)
    - **display_name**: full name (optional, will be set to '$name' if unset)
    - **educational_servers**: hosts names of educational DCs (optional, each max. 13 chars long,
        'dc$name' will automatically be created and added if unset, more than one DC is **not**
        supported)
    - **administrative_servers**: host names of administrative DCs (optional, each max. 13 chars long,
        more than one DC is **not** supported)
    - **class_share_file_server**: host names of DCs for the class shares (optional,
        will be alphabetically first of '$educational_servers' if unset)
    - **home_share_file_server**: host names of DCs for the home shares (optional,
        will be alphabetically first of '$educational_servers' if unset)
    - **udm_properties**: object with UDM properties (optional, e.g.
        **{"udm_prop1": "value1"}**, must be configured in
        **mapped_udm_properties**, see documentation)

    **JSON Example**:

        {
            "udm_properties": {},
            "name": "EXAMPLESCHOOL",
            "display_name": "Example School"
        }
    """
    school_obj: School = school.as_lib_model(request)
    if await school_obj.exists(udm):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="School exists.")
    await validate_create_request_params(school, logger, udm)
    admin_name = sorted(school.administrative_servers)[0] if school.administrative_servers else None
    edu_name = sorted(school.educational_servers)[0] if school.educational_servers else None
    share_server = school.home_share_file_server or school.class_share_file_server
    create_kwargs = {
        "ou_name": school.name,
        "display_name": school.display_name,
        "edu_name": edu_name,
        "admin_name": admin_name,
        "share_name": share_server,
        "lo": udm,
        "baseDN": env_or_ucr("ldap/base"),
        "hostname": env_or_ucr("ldap/master").split(".", 1)[0],
        "is_single_master": env_or_ucr("ucsschool/singlemaster"),
        "alter_dhcpd_base": alter_dhcpd_base,
    }
    logger.debug("Creating school with: %r", create_kwargs)
    try:
        await create_ou(**create_kwargs)
    except ValueError as exc:
        error_msg = f"Failed to create school with parameters {school.dict()!r}: {exc}"
        logger.exception(error_msg)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error_msg)
    except Exception as exc:
        error_msg = f"Failed to create school {school_obj.name!r}: {exc}"
        logger.exception(error_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)
    await _remove_ou_from_cache(school.name)
    background_tasks.add_task(ImportUser.update_all_school_names_cache)
    school_obj_to_fix = await School.from_dn(school_obj.dn, school_obj.name, udm)
    school_obj_to_fix.udm_properties = school_obj.udm_properties
    logger.debug("Finished create_ou(), fixing schools DC attributes...")
    try:
        await fix_school_attributes(school_obj_to_fix, school, logger, udm)
    except UDMPropertiesError as exc:
        error_msg = f"Failed to set udm properties on newly created school {school_obj.name!r}: {exc}"
        logger.exception(error_msg)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg)
    return await SchoolModel.from_lib_model(school_obj_to_fix, request, udm)


@router.head("/{school_name}")
async def school_exists(
    school_name: str = Path(
        default=...,
        description="School (OU) with this name.",
        title="name",
    ),
    kelvin_admin: LdapUser = Depends(get_kelvin_admin),
):
    """
    Check if school (OU) with a provided name exists.

    - **name**: name of the school (**required**)
    """

    # Always do a fresh LDAP search for this resource. Don't use value from cache.
    # (As a side effect, this will add/update the cache entry for `school_name`.)
    await _remove_ou_from_cache(school_name)

    results = await search_schools_in_ldap(school_name, raise404=False)
    status_code = status.HTTP_200_OK if results else status.HTTP_404_NOT_FOUND
    return Response(status_code=status_code)


@cached(ttl=OU_CACHE_TTL, cache=Cache.MEMORY, namespace=OU_CACHE_NAMESPACE, key_builder=ou_cache_key)
async def _search_schools_in_ldap(ou: str) -> List[str]:
    uldap = uldap_admin_read_local()
    results = uldap.search(
        filter_format("(&(objectClass=ucsschoolOrganizationalUnit)(ou=%s))", (ou,)),
        attributes=["ou"],
    )
    return [r["ou"].value for r in results]


async def search_schools_in_ldap(ou: str, *, raise404: bool = False) -> List[str]:
    """Get names of school OUs matching `ou`. Optionally raise HTTPException(404)."""
    ous = await _search_schools_in_ldap(ou)
    if not ous and raise404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No school with name={ou!r} found.",
        )
    return ous


async def _remove_ou_from_cache(ou: str) -> None:
    cache = _search_schools_in_ldap.cache
    cache_key = ou_cache_key(_search_schools_in_ldap, ou)
    await cache.delete(cache_key, namespace=OU_CACHE_NAMESPACE)
