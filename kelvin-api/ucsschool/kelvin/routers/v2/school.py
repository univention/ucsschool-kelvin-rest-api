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

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from ucsschool_objects import (
    Filter,
    KelvinStorageSession,
    Operator,
    School,
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
from ..v1.school import (
    SchoolModel,
    school_create,
    school_exists as v1_school_exists,
    school_get as v1_school_get,
    school_search as v1_school_search,
)
from .udm_properties import mapped_udm_properties

router = APIRouter()


@lru_cache(maxsize=1)
def get_logger() -> logging.Logger:
    return logging.getLogger(__name__)


def _str_filter(field: str, value: str) -> Filter:
    if "*" in value:
        return Filter(field=field, op=Operator.LIKE, value=value.replace("*", "%"))
    return Filter(field=field, op=Operator.EQ, value=value)


async def _school_to_model(
    school: School, request: Request, session: KelvinStorageSession
) -> SchoolModel:
    mapper = sqlalchemy_mapper_factory(session)
    dn_map = await mapper.public_ids_to_dns(ObjectType.SCHOOL, [school.public_id])
    dn = dn_map.get(school.public_id, "")

    return SchoolModel(
        name=school.name,
        display_name=school.display_name or None,
        educational_servers=sorted(school.educational_servers) if school.educational_servers else [],
        administrative_servers=sorted(school.administrative_servers)
        if school.administrative_servers
        else [],
        class_share_file_server=school.class_share_file_server,
        home_share_file_server=school.home_share_file_server,
        url=SchoolModel.scheme_and_quote(
            str(cached_url_for(request, "school_get", school_name=school.name))
        ),
        dn=dn,
        ucsschool_roles=[f"school:school:{school.name}"],
        udm_properties=mapped_udm_properties(school.udm_properties, "school"),
    )


@router.get("/", response_model=List[SchoolModel])
async def search(
    request: Request,
    name_filter: Optional[str] = Query(
        None,
        alias="name",
        description="List schools with this name. '*' can be used for an inexact search. (optional)",
        title="name",
    ),
    logger: logging.Logger = Depends(get_logger),
    session: KelvinStorageSession = Depends(get_storage_session),
    kelvin_reader: LdapUser = Depends(get_kelvin_reader),
) -> List[SchoolModel]:
    query = SearchQuery(where=_str_filter("name", name_filter)) if name_filter else None
    logger.debug("v2 school search query: %r", query)
    schools = list(await session.schools.search(query))
    schools.sort(key=lambda s: s.name)
    return [await _school_to_model(s, request, session) for s in schools]


@router.get("/{school_name}", response_model=SchoolModel)
async def school_get(
    request: Request,
    school_name: str = Path(
        ...,
        description="School (OU) with this name.",
        title="name",
    ),
    logger: logging.Logger = Depends(get_logger),
    session: KelvinStorageSession = Depends(get_storage_session),
    kelvin_reader: LdapUser = Depends(get_kelvin_reader),
) -> SchoolModel:
    results = list(
        await session.schools.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value=school_name))
        )
    )
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No school with name={school_name!r} found.",
        )
    logger.debug("v2 school get: %r", school_name)
    return await _school_to_model(results[0], request, session)


@router.head("/{school_name}")
async def school_exists(
    school_name: str = Path(
        ...,
        description="School (OU) with this name.",
        title="name",
    ),
    session: KelvinStorageSession = Depends(get_storage_session),
    kelvin_reader: LdapUser = Depends(get_kelvin_reader),
):
    results = list(
        await session.schools.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value=school_name)),
            limit=1,
        )
    )
    return Response(status_code=status.HTTP_200_OK if results else status.HTTP_404_NOT_FOUND)


router.add_api_route(
    "/",
    school_create,
    methods=["POST"],
    status_code=status.HTTP_201_CREATED,
    response_model=SchoolModel,
)

search.__doc__ = v1_school_search.__doc__
school_get.__doc__ = v1_school_get.__doc__
school_exists.__doc__ = v1_school_exists.__doc__
