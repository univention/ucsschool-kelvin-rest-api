# SPDX-FileCopyrightText: 2020-2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from ucsschool_objects import (
    Filter,
    KelvinStorageSession,
    LoadSpec,
    Operator,
    Role,
    SearchQuery,
)

from ...ldap import LdapUser
from ...service.dependency import get_storage_session
from ...token_auth import get_kelvin_reader
from ..v1.role import RoleModel, SchoolUserRole, get as v1_get, search as v1_search
from ._pagination import ModelPageResponse, Page, PageRequest, page_request, page_response, search_page
from ._responses import ModelListResponse

router = APIRouter()


@lru_cache(maxsize=1)
def get_logger() -> logging.Logger:
    return logging.getLogger(__name__)


ROLE_LOAD_SPEC_V2 = LoadSpec.from_attributes("name", "display_name")

_KNOWN_ROLE_NAMES = frozenset(role.value for role in SchoolUserRole)


# Roles of other kinds share the table; leaving them out in the query keeps
# the pages of a limited search full.
_KNOWN_ROLES_QUERY = SearchQuery(
    where=Filter(field="name", op=Operator.IN, value=tuple(sorted(_KNOWN_ROLE_NAMES)))
)


def _role_to_model(role: Role, request: Request) -> RoleModel:
    return RoleModel(
        name=role.name,
        display_name=role.name,
        url=SchoolUserRole(role.name).to_url(request),
    )


@router.get("/", response_model=list[RoleModel] | Page[RoleModel])
async def search(
    request: Request,
    page: Annotated[PageRequest | None, Depends(page_request)],
    logger: Annotated[logging.Logger, Depends(get_logger)],
    session: Annotated[KelvinStorageSession, Depends(get_storage_session)],
    kelvin_reader: Annotated[LdapUser, Depends(get_kelvin_reader)],
) -> ModelListResponse[RoleModel] | ModelPageResponse[RoleModel]:
    if page is None:
        roles = sorted(
            await session.roles.search(_KNOWN_ROLES_QUERY, load=ROLE_LOAD_SPEC_V2),
            key=lambda r: r.name,
        )
        logger.debug("v2 role search: found %d known roles", len(roles))
        return ModelListResponse([_role_to_model(role, request) for role in roles])
    found = await search_page(
        session.roles, _KNOWN_ROLES_QUERY, page, lambda r: r.name, load=ROLE_LOAD_SPEC_V2
    )
    logger.debug("v2 role search: found %d known roles on the page", len(found.items))
    return page_response(request, found, [_role_to_model(role, request) for role in found.items])


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
