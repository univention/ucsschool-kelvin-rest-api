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
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from ucsschool_objects import (
    Filter,
    KelvinStorageSession,
    LoadSpec,
    Operator,
    SearchQuery,
)

from ...ldap import LdapUser
from ...service.dependency import get_storage_session
from ...token_auth import get_kelvin_reader
from ..v1.role import RoleModel, SchoolUserRole, get as v1_get, search as v1_search

router = APIRouter()


@lru_cache(maxsize=1)
def get_logger() -> logging.Logger:
    return logging.getLogger(__name__)


ROLE_LOAD_SPEC_V2 = LoadSpec.from_attributes("name", "display_name")

_KNOWN_ROLE_NAMES = frozenset(role.value for role in SchoolUserRole)


@router.get("/", response_model=List[RoleModel])
async def search(
    request: Request,
    logger: logging.Logger = Depends(get_logger),
    session: KelvinStorageSession = Depends(get_storage_session),
    kelvin_reader: LdapUser = Depends(get_kelvin_reader),
) -> List[RoleModel]:
    roles = sorted(
        [
            role
            for role in await session.roles.search(load=ROLE_LOAD_SPEC_V2)
            if role.name in _KNOWN_ROLE_NAMES
        ],
        key=lambda r: r.name,
    )
    logger.debug("v2 role search: found %d known roles", len(roles))
    return [
        RoleModel(
            name=role.name,
            display_name=role.name,
            url=SchoolUserRole(role.name).to_url(request),
        )
        for role in roles
    ]


@router.get("/{role_name}", response_model=RoleModel)
async def get(
    request: Request,
    role_name: str = Path(..., description="Name of the role to fetch."),
    logger: logging.Logger = Depends(get_logger),
    session: KelvinStorageSession = Depends(get_storage_session),
    kelvin_reader: LdapUser = Depends(get_kelvin_reader),
) -> RoleModel:
    try:
        school_role = SchoolUserRole(role_name)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No object with name={role_name!r} found or not authorized.",
        )
    results = list(
        await session.roles.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value=role_name)),
            load=ROLE_LOAD_SPEC_V2,
        )
    )
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No object with name={role_name!r} found or not authorized.",
        )
    logger.debug("v2 role get: %r", role_name)
    return RoleModel(
        name=role_name,
        display_name=role_name,
        url=school_role.to_url(request),
    )


search.__doc__ = v1_search.__doc__
get.__doc__ = v1_get.__doc__
