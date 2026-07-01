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
from typing import Annotated

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
from ..v1.workgroup import (
    WorkGroupModel,
    complete_update,
    create,
    delete,
    get as v1_get,
    partial_update,
    search as v1_search,
)
from ._filters import str_filter as _str_filter
from .udm_properties import mapped_udm_properties

router = APIRouter()

_WORKGROUP_ROLE = "workgroup"

WORKGROUP_LOAD_SPEC_V2 = LoadSpec.from_attributes(
    "name",
    "display_name",
    "create_share",
    "email",
    "roles",
    "members",
    "allowed_email_senders_users",
    "allowed_email_senders_groups",
    "description",
    "udm_properties",
)


@lru_cache(maxsize=1)
def get_logger() -> logging.Logger:
    return logging.getLogger(__name__)


def _get_relative_name(group: Group) -> str:
    """Strip school prefix from group name (e.g. 'SCHOOL-wgname' -> 'wgname')."""
    school_name = group.school.name
    if group.name.lower().startswith(f"{school_name.lower()}-"):
        return group.name[len(school_name) + 1 :]
    return group.name


def _is_workgroup(group: Group) -> bool:
    return _WORKGROUP_ROLE in {role.name for role in group.roles}


async def _group_to_workgroup_model(
    group: Group, request: Request, session: KelvinStorageSession
) -> WorkGroupModel:
    mapper = sqlalchemy_mapper_factory(session)

    user_public_ids = [u.public_id for u in group.allowed_email_senders_users]
    group_public_ids = [g.public_id for g in group.allowed_email_senders_groups]

    dn_map = await mapper.public_ids_to_dns(ObjectType.GROUP, [group.public_id] + group_public_ids)
    dn = dn_map.get(group.public_id, "")

    allowed_email_senders_groups = sorted(dn_map[pid] for pid in group_public_ids if pid in dn_map)

    if user_public_ids:
        user_dn_map = await mapper.public_ids_to_dns(ObjectType.USER, user_public_ids)
        allowed_email_senders_users = sorted(user_dn_map.values())
    else:
        allowed_email_senders_users = []

    relative_name = _get_relative_name(group)
    school_name = group.school.name

    users = sorted(
        WorkGroupModel.scheme_and_quote(str(cached_url_for(request, "get", username=user.name)))
        for user in group.members
    )

    ucsschool_roles = sorted(f"{role.name}:school:{school_name}" for role in group.roles)

    return WorkGroupModel(
        name=relative_name,
        school=WorkGroupModel.scheme_and_quote(
            str(cached_url_for(request, "school_get", school_name=school_name))
        ),
        description=group.description,
        users=users,
        create_share=group.create_share,
        email=group.email,
        allowed_email_senders_users=allowed_email_senders_users,
        allowed_email_senders_groups=allowed_email_senders_groups,
        ucsschool_roles=ucsschool_roles,
        url=WorkGroupModel.scheme_and_quote(
            str(cached_url_for(request, "get", workgroup_name=relative_name, school=school_name))
        ),
        dn=dn,
        udm_properties=mapped_udm_properties(group.udm_properties, "workgroup"),
    )


@router.get("/", response_model=list[WorkGroupModel])
async def search(
    request: Request,
    school: Annotated[
        str,
        Query(
            ...,
            description=(
                "Name of school (``OU``) in which to search for workgroups "
                "(**case sensitive, exact match, required**)."
            ),
            min_length=2,
        ),
    ],
    workgroup_name: Annotated[
        str | None,
        Query(
            None,
            alias="name",
            description=(
                "List workgroups with this name. "
                "(optional, ``*`` can be used "
                "for an inexact search)."
            ),
            title="name",
        ),
    ],
    logger: Annotated[logging.Logger, Depends(get_logger)],
    session: Annotated[KelvinStorageSession, Depends(get_storage_session)],
    _kelvin_reader: Annotated[LdapUser, Depends(get_kelvin_reader)],
) -> list[WorkGroupModel]:
    clauses = [Filter(field="school.name", op=Operator.EQ, value=school)]
    if workgroup_name:
        clauses.append(_str_filter("name", f"{school}-{workgroup_name}"))
    query = SearchQuery(where=And(clauses=tuple(clauses)) if len(clauses) > 1 else clauses[0])
    logger.debug("v2 workgroup search query: %r", query)
    groups = [
        g for g in await session.groups.search(query, load=WORKGROUP_LOAD_SPEC_V2) if _is_workgroup(g)
    ]
    groups.sort(key=lambda g: g.name)
    return [await _group_to_workgroup_model(g, request, session) for g in groups]


@router.get("/{school}/{workgroup_name}", response_model=WorkGroupModel)
async def get(
    request: Request,
    workgroup_name: Annotated[str, Path(description="Name of the workgroup to fetch.")],
    school: Annotated[str, Path(description="Name of the school (OU).")],
    logger: Annotated[logging.Logger, Depends(get_logger)],
    session: Annotated[KelvinStorageSession, Depends(get_storage_session)],
    _kelvin_reader: Annotated[LdapUser, Depends(get_kelvin_reader)],
) -> WorkGroupModel:
    full_name = f"{school}-{workgroup_name}"
    results = [
        g
        for g in await session.groups.search(
            SearchQuery(where=Filter(field="name", op=Operator.MATCHES_CI, value=full_name)),
            load=WORKGROUP_LOAD_SPEC_V2,
        )
        if _is_workgroup(g)
    ]
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No object with name={workgroup_name!r} found or not authorized.",
        )
    logger.debug("v2 workgroup get: %r in school %r", workgroup_name, school)
    return await _group_to_workgroup_model(results[0], request, session)


router.add_api_route(
    "/",
    create,
    methods=["POST"],
    status_code=status.HTTP_201_CREATED,
    response_model=WorkGroupModel,
)
router.add_api_route(
    "/{school}/{workgroup_name}",
    partial_update,
    methods=["PATCH"],
    status_code=status.HTTP_200_OK,
    response_model=WorkGroupModel,
)
router.add_api_route(
    "/{school}/{workgroup_name}",
    complete_update,
    methods=["PUT"],
    status_code=status.HTTP_200_OK,
    response_model=WorkGroupModel,
)
router.add_api_route(
    "/{school}/{workgroup_name}",
    delete,
    methods=["DELETE"],
    status_code=status.HTTP_204_NO_CONTENT,
)

search.__doc__ = v1_search.__doc__
get.__doc__ = v1_get.__doc__
