# SPDX-FileCopyrightText: 2020-2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import logging
from functools import lru_cache
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from ucsschool_objects import (
    Filter,
    Group,
    KelvinStorageSession,
    LoadSpec,
    Operator,
    SearchQuery,
    User,
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
from ._filters import group_search_query as _group_search_query
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


def _public_id(obj: Group | User) -> UUID:
    """A loaded object's public id.

    Typed ``UUID | UnsetType`` on the domain object, because an attribute the
    load spec leaves out reads as unset. ``public_id`` is never left out.
    """
    return cast("UUID", obj.public_id)


def _is_workgroup(group: Group) -> bool:
    return _WORKGROUP_ROLE in {role.name for role in group.roles}


def _workgroup_dn_subjects(group: Group) -> tuple[list[UUID], list[UUID]]:
    """The group and user ids one work group needs resolved to DNs.

    The work group itself, the groups allowed to mail it, and the users allowed
    to mail it - collected so a search can resolve a page of them at once.
    """
    return (
        [_public_id(group)] + [_public_id(g) for g in group.allowed_email_senders_groups],
        [_public_id(u) for u in group.allowed_email_senders_users],
    )


async def _group_to_workgroup_model(
    group: Group,
    request: Request,
    session: KelvinStorageSession,
    dn_map: dict[UUID, str] | None = None,
    user_dn_map: dict[UUID, str] | None = None,
) -> WorkGroupModel:
    group_public_ids = [_public_id(g) for g in group.allowed_email_senders_groups]
    user_public_ids = [_public_id(u) for u in group.allowed_email_senders_users]

    if dn_map is None or user_dn_map is None:
        mapper = sqlalchemy_mapper_factory(session)
        dn_map = await mapper.public_ids_to_dns(ObjectType.GROUP, [_public_id(group)] + group_public_ids)
        user_dn_map = (
            await mapper.public_ids_to_dns(ObjectType.USER, user_public_ids) if user_public_ids else {}
        )
    dn = dn_map.get(_public_id(group), "")

    allowed_email_senders_groups = sorted(dn_map[pid] for pid in group_public_ids if pid in dn_map)
    allowed_email_senders_users = sorted(
        user_dn_map[pid] for pid in user_public_ids if pid in user_dn_map
    )

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
    logger: Annotated[logging.Logger, Depends(get_logger)],
    session: Annotated[KelvinStorageSession, Depends(get_storage_session)],
    _kelvin_reader: Annotated[LdapUser, Depends(get_kelvin_reader)],
    workgroup_name: Annotated[
        list[str] | None,
        Query(
            alias="name",
            description=(
                "List workgroups with these names. Repeat the parameter to ask for "
                "several at once; each value may use ``*`` as a case-insensitive "
                "wildcard. (optional)"
            ),
            title="name",
        ),
    ] = None,
) -> list[WorkGroupModel]:
    query = _group_search_query(school, workgroup_name)
    logger.debug("v2 workgroup search query: %r", query)
    groups = [
        g for g in await session.groups.search(query, load=WORKGROUP_LOAD_SPEC_V2) if _is_workgroup(g)
    ]
    groups.sort(key=lambda g: g.name)
    # Two lookups for the whole page, as the user search already does: resolving
    # them per group is two round trips per group.
    mapper = sqlalchemy_mapper_factory(session)
    subjects = [_workgroup_dn_subjects(g) for g in groups]
    dn_map = await mapper.public_ids_to_dns(
        ObjectType.GROUP, [pid for group_ids, _user_ids in subjects for pid in group_ids]
    )
    user_ids = [pid for _group_ids, user_ids in subjects for pid in user_ids]
    user_dn_map = await mapper.public_ids_to_dns(ObjectType.USER, user_ids) if user_ids else {}
    return [
        await _group_to_workgroup_model(g, request, session, dn_map=dn_map, user_dn_map=user_dn_map)
        for g in groups
    ]


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
    # LDAP keeps group names unique regardless of case, but the Kelvin DB only
    # catches up eventually: a group deleted outside Kelvin can still be cached
    # next to a newly created one that differs only in case. The exact spelling
    # wins, so such a pair never answers with the stale one.
    results = sorted(
        (
            g
            for g in await session.groups.search(
                SearchQuery(where=Filter(field="name", op=Operator.IN_CI, value=(full_name,))),
                load=WORKGROUP_LOAD_SPEC_V2,
            )
            if _is_workgroup(g)
        ),
        key=lambda g: g.name != full_name,
    )
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
