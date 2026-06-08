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
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from ucsschool_objects import (
    And,
    Filter,
    Group,
    KelvinStorageSession,
    LoadSpec,
    Operator,
    SearchQuery,
)
from ucsschool_objects.core.adapters.sqlalchemy import (
    sqlalchemy_mapper_factory,
)
from ucsschool_objects.core.domain.ports.dn_mapper import ObjectType

from ...ldap import LdapUser
from ...service.dependency import get_storage_session
from ...token_auth import get_kelvin_reader
from ...urls import cached_url_for
from ..v1.school_class import (
    SchoolClassModel,
    complete_update,
    create,
    delete,
    get as v1_get,
    partial_update,
    search as v1_search,
)
from .udm_properties import mapped_udm_properties

router = APIRouter()

_SCHOOL_CLASS_ROLE = "school_class"

SCHOOL_CLASS_LOAD_SPEC_V2 = LoadSpec.from_attributes(
    "name",
    "display_name",
    "create_share",
    "roles",
    "members",
    "description",
    "udm_properties",
)


@lru_cache(maxsize=1)
def get_logger() -> logging.Logger:
    return logging.getLogger(__name__)


def _str_filter(field: str, value: str) -> Filter:
    if "*" in value:
        return Filter(field=field, op=Operator.LIKE, value=value.replace("*", "%"))
    return Filter(field=field, op=Operator.EQ, value=value)


def _get_relative_name(group: Group) -> str:
    """Strip school prefix from group name (e.g. 'SCHOOL-classname' -> 'classname')."""
    school_name = group.school.name
    if group.name.lower().startswith(f"{school_name.lower()}-"):
        return group.name[len(school_name) + 1 :]
    return group.name


def _is_school_class(group: Group) -> bool:
    return _SCHOOL_CLASS_ROLE in {role.name for role in group.roles}


async def _group_to_school_class_model(
    group: Group, request: Request, session: KelvinStorageSession
) -> SchoolClassModel:
    mapper = sqlalchemy_mapper_factory(session)
    dn_map = await mapper.public_ids_to_dns(ObjectType.GROUP, [group.public_id])
    dn = dn_map.get(group.public_id, "")

    relative_name = _get_relative_name(group)
    school_name = group.school.name

    users = sorted(
        SchoolClassModel.scheme_and_quote(str(cached_url_for(request, "get", username=user.name)))
        for user in group.members
    )

    ucsschool_roles = sorted(f"{role.name}:school:{school_name}" for role in group.roles)

    return SchoolClassModel(
        name=relative_name,
        school=SchoolClassModel.scheme_and_quote(
            str(cached_url_for(request, "school_get", school_name=school_name))
        ),
        description=group.description,
        users=users,
        create_share=group.create_share,
        ucsschool_roles=ucsschool_roles,
        url=SchoolClassModel.scheme_and_quote(
            str(cached_url_for(request, "get", class_name=relative_name, school=school_name))
        ),
        dn=dn,
        udm_properties=mapped_udm_properties(group.udm_properties, "school_class"),
    )


@router.get("/", response_model=List[SchoolClassModel])
async def search(
    request: Request,
    school: str = Query(
        ...,
        description="Name of school (``OU``) in which to search for classes "
        "(**case sensitive, exact match, required**).",
        min_length=2,
    ),
    class_name: Optional[str] = Query(
        None,
        alias="name",
        description="List classes with this name. (optional, ``*`` can be used for an inexact search).",
        title="name",
    ),
    logger: logging.Logger = Depends(get_logger),
    session: KelvinStorageSession = Depends(get_storage_session),
    kelvin_reader: LdapUser = Depends(get_kelvin_reader),
) -> List[SchoolClassModel]:
    clauses = [Filter(field="school.name", op=Operator.EQ, value=school)]
    if class_name:
        clauses.append(_str_filter("name", f"{school}-{class_name}"))
    query = SearchQuery(where=And(clauses=tuple(clauses)) if len(clauses) > 1 else clauses[0])
    logger.debug("v2 school_class search query: %r", query)
    groups = [
        g
        for g in await session.groups.search(query, load=SCHOOL_CLASS_LOAD_SPEC_V2)
        if _is_school_class(g)
    ]
    groups.sort(key=lambda g: g.name)
    return [await _group_to_school_class_model(g, request, session) for g in groups]


@router.get("/{school}/{class_name}", response_model=SchoolClassModel)
async def get(
    request: Request,
    class_name: str = Path(..., description="Name of the school class to fetch."),
    school: str = Path(..., description="Name of the school (OU)."),
    logger: logging.Logger = Depends(get_logger),
    session: KelvinStorageSession = Depends(get_storage_session),
    kelvin_reader: LdapUser = Depends(get_kelvin_reader),
) -> SchoolClassModel:
    full_name = f"{school}-{class_name}"
    results = [
        g
        for g in await session.groups.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value=full_name)),
            load=SCHOOL_CLASS_LOAD_SPEC_V2,
        )
        if _is_school_class(g)
    ]
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No object with name={class_name!r} found or not authorized.",
        )
    logger.debug("v2 school_class get: %r in school %r", class_name, school)
    return await _group_to_school_class_model(results[0], request, session)


router.add_api_route(
    "/",
    create,
    methods=["POST"],
    status_code=status.HTTP_201_CREATED,
    response_model=SchoolClassModel,
)
router.add_api_route(
    "/{school}/{class_name}",
    partial_update,
    methods=["PATCH"],
    status_code=status.HTTP_200_OK,
    response_model=SchoolClassModel,
)
router.add_api_route(
    "/{school}/{class_name}",
    complete_update,
    methods=["PUT"],
    status_code=status.HTTP_200_OK,
    response_model=SchoolClassModel,
)
router.add_api_route(
    "/{school}/{class_name}",
    delete,
    methods=["DELETE"],
    status_code=status.HTTP_204_NO_CONTENT,
)

search.__doc__ = v1_search.__doc__
get.__doc__ = v1_get.__doc__
