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

import datetime
import logging
from functools import lru_cache
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from ucsschool_objects import (
    And,
    Filter,
    KelvinStorageSession,
    LoadSpec,
    ObjectType,
    Operator,
    Or,
    QueryExpr,
    SearchQuery,
    User,
    make_wildcard_filter,
)
from ucsschool_objects.core.adapters.sqlalchemy import (
    sqlalchemy_mapper_factory,
)

from ...config import UDM_MAPPING_CONFIG
from ...ldap import LdapUser
from ...service.dependency import get_storage_session
from ...token_auth import get_kelvin_reader
from ...urls import cached_url_for
from ..v1.role import SchoolUserRole
from ..v1.user import (
    UserModel,
    complete_update,
    create,
    delete,
    get as v1_get,
    partial_update,
    search as v1_search,
)
from .udm_properties import mapped_udm_properties

router = APIRouter()


@lru_cache(maxsize=1)
def get_logger() -> logging.Logger:
    return logging.getLogger(__name__)


logger = get_logger()

USER_LOAD_SPEC_V2 = LoadSpec.from_attributes(
    "record_uid",
    "source_uid",
    "name",
    "firstname",
    "lastname",
    "active",
    "school_memberships",
    "legal_wards",
    "legal_guardians",
    "public_id",
    "email",
    "birthday",
    "expiration_date",
    "udm_properties",
)


def _str_filter(field: str, value: str) -> Filter:
    """Create a string filter with wildcard support and proper escaping."""
    return (
        make_wildcard_filter(field, value)
        if "*" in value
        else Filter(field=field, op=Operator.EQ, value=value)
    )


_KNOWN_SEARCH_PARAMS = frozenset(
    {
        "school",
        "name",
        "firstname",
        "lastname",
        "email",
        "record_uid",
        "source_uid",
        "birthday",
        "expiration_date",
        "disabled",
    }
)


def _udm_property_filters(request: Request) -> list[QueryExpr]:
    """Filters for configured mapped UDM properties given as query parameters.

    Mirrors v1: parameters that are neither known search parameters nor
    configured mapped properties are silently ignored. CONTAINS matches both
    scalar values (equality) and elements of multi-valued properties such as
    e-mail or phone. Digit values also compare as integers (e.g. uidNumber);
    '*' acts as a wildcard on scalar values.
    """
    configured = set(UDM_MAPPING_CONFIG.user)
    filters: list[QueryExpr] = []
    for param, value in request.query_params.items():
        if param in _KNOWN_SEARCH_PARAMS or param not in configured:
            continue
        field = f"udm_properties.{param}"
        if value.lstrip("-").isdigit():
            # The stored JSON value may be a number, a string of digits, or
            # a list containing one (e.g. phone numbers).
            sliced_value = value.lstrip("-")
            filters.append(
                Or(
                    clauses=(
                        Filter(field=field, op=Operator.EQ, value=int(sliced_value)),
                        Filter(field=field, op=Operator.CONTAINS, value=sliced_value),
                    )
                )
            )
        elif "*" in value:
            filters.append(make_wildcard_filter(field, value))
        else:
            filters.append(Filter(field=field, op=Operator.CONTAINS, value=value))
    return filters


def _build_query(
    school: Optional[str],
    name: Optional[str],
    firstname: Optional[str],
    lastname: Optional[str],
    email: Optional[str],
    record_uid: Optional[str],
    source_uid: Optional[str],
    birthday: Optional[datetime.date],
    expiration_date: Optional[datetime.date],
    disabled: Optional[bool],
    extra_clauses: Optional[list[QueryExpr]] = None,
) -> Optional[SearchQuery]:
    clauses: list[QueryExpr] = list(extra_clauses or [])
    if name:
        clauses.append(_str_filter("name", name))
    if school:
        clauses.append(_str_filter("schools.name", school))
    if firstname:
        clauses.append(_str_filter("firstname", firstname))
    if lastname:
        clauses.append(_str_filter("lastname", lastname))
    if email:
        clauses.append(Filter(field="email", op=Operator.EQ, value=email))
    if record_uid:
        clauses.append(_str_filter("record_uid", record_uid))
    if source_uid:
        clauses.append(_str_filter("source_uid", source_uid))
    if birthday is not None:
        clauses.append(Filter(field="birthday", op=Operator.EQ, value=birthday))
    if expiration_date is not None:
        clauses.append(Filter(field="expiration_date", op=Operator.EQ, value=expiration_date))
    if disabled is not None:
        clauses.append(Filter(field="active", op=Operator.EQ, value=not disabled))

    if not clauses:
        return None
    if len(clauses) == 1:
        return SearchQuery(where=clauses[0])
    return SearchQuery(where=And(clauses=tuple(clauses)))


def _school_classes_and_workgroups(
    user: User,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    # Only schools that actually have a class/workgroup get an entry, matching
    # v1 — do not pre-seed every membership's school with an empty list.
    school_classes: dict[str, list[str]] = {}
    workgroups: dict[str, list[str]] = {}

    for group in user.groups:
        role_names = [role.name for role in group.roles]
        relative_name = group.name.removeprefix(f"{group.school.name}-")
        if "school_class" in role_names:
            school_classes.setdefault(group.school.name, []).append(relative_name)
        if "workgroup" in role_names:
            workgroups.setdefault(group.school.name, []).append(relative_name)

    # user.groups is a set, so the per-school lists are built in arbitrary
    # order; sort them for deterministic, v1-equivalent output.
    for names in school_classes.values():
        names.sort()
    for names in workgroups.values():
        names.sort()

    return school_classes, workgroups


async def _user_to_model(
    user: User,
    request: Request,
    session: KelvinStorageSession,
    dn_map: dict[UUID, str] | None = None,
) -> UserModel:
    def url(name: str, **kwargs) -> str:
        return UserModel.scheme_and_quote(str(cached_url_for(request, name, **kwargs)))

    if dn_map is None:
        mapper = sqlalchemy_mapper_factory(session)
        dn_map = await mapper.public_ids_to_dns(ObjectType.USER, [user.public_id])
    dn = dn_map[user.public_id]

    schools = sorted(
        url("school_get", school_name=school_membership.school.name)
        for school_membership in user.school_memberships.values()
    )

    ucsschool_roles: list[str] = []
    for membership in user.school_memberships.values():
        for role in membership.roles:
            ucsschool_roles.append(f"{role.name}:school:{membership.school.name}")

    roles: set[SchoolUserRole] = set()

    for role in user.roles:
        try:
            roles.add(SchoolUserRole(role.name))
        except ValueError:
            logger.error(f"Unknown role name: {role.name=}. Omitting role.")

    school_classes, workgroups = _school_classes_and_workgroups(user)

    role_urls = [url("get", role_name=role.value) for role in sorted(roles)]

    legal_guardian_urls = [url("get", username=guardian.name) for guardian in user.legal_guardians]
    legal_ward_urls = [url("get", username=ward.name) for ward in user.legal_wards]

    school = url("school_get", school_name=user.primary_school.name)

    return UserModel(
        school=school,
        dn=dn,
        name=user.name,
        firstname=user.firstname,
        lastname=user.lastname,
        birthday=user.birthday,
        disabled=not user.active,
        email=user.email,
        expiration_date=user.expiration_date,
        record_uid=user.record_uid,
        source_uid=user.source_uid,
        url=url("get", username=user.name),
        schools=schools,
        roles=role_urls,
        school_classes=school_classes,
        workgroups=workgroups,
        ucsschool_roles=ucsschool_roles,
        legal_guardians=legal_guardian_urls,
        legal_wards=legal_ward_urls,
        udm_properties=mapped_udm_properties(user.udm_properties, "user"),
    )


@router.get("/", response_model=List[UserModel])
async def search(
    request: Request,
    school: str = Query(
        None,
        description="List only users that are members of matching school(s) (OUs).",
    ),
    username: str = Query(
        None, alias="name", description="List users with this username.", title="name"
    ),
    firstname: str = Query(None),
    lastname: str = Query(None),
    email: str = Query(None),
    record_uid: str = Query(None),
    source_uid: str = Query(None),
    birthday: datetime.date = Query(None, description="Exact match only. Format must be YYYY-MM-DD."),
    expiration_date: datetime.date = Query(
        None, description="Exact match only. Format must be YYYY-MM-DD."
    ),
    disabled: bool = Query(None),
    logger: logging.Logger = Depends(get_logger),
    session: KelvinStorageSession = Depends(get_storage_session),
    kelvin_reader: LdapUser = Depends(get_kelvin_reader),
) -> List[UserModel]:
    query = _build_query(
        school=school,
        name=username,
        firstname=firstname,
        lastname=lastname,
        email=email,
        record_uid=record_uid,
        source_uid=source_uid,
        birthday=birthday,
        expiration_date=expiration_date,
        disabled=disabled,
        extra_clauses=_udm_property_filters(request),
    )
    logger.debug("v2 user search query: %r", query)
    users = list(await session.users.search(query, load=USER_LOAD_SPEC_V2))
    users.sort(key=lambda u: u.name)
    mapper = sqlalchemy_mapper_factory(session)
    dn_map = await mapper.public_ids_to_dns(ObjectType.USER, [user.public_id for user in users])
    return [await _user_to_model(u, request, session, dn_map=dn_map) for u in users]


@router.get("/{username}", response_model=UserModel)
async def get(
    request: Request,
    username: str = Path(..., description="Name of the school user to fetch."),
    logger: logging.Logger = Depends(get_logger),
    session: KelvinStorageSession = Depends(get_storage_session),
    kelvin_reader: LdapUser = Depends(get_kelvin_reader),
) -> UserModel:
    results = list(
        await session.users.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value=username)),
            load=USER_LOAD_SPEC_V2,
        )
    )
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No object with name={username!r} found or not authorized.",
        )
    return await _user_to_model(results[0], request, session, dn_map=None)


router.add_api_route(
    "/",
    create,
    methods=["POST"],
    status_code=status.HTTP_201_CREATED,
    response_model=UserModel,
)
router.add_api_route(
    "/{username}",
    partial_update,
    methods=["PATCH"],
    status_code=status.HTTP_200_OK,
    response_model=UserModel,
)
router.add_api_route(
    "/{username}",
    complete_update,
    methods=["PUT"],
    status_code=status.HTTP_200_OK,
    response_model=UserModel,
)
router.add_api_route(
    "/{username}",
    delete,
    methods=["DELETE"],
    status_code=status.HTTP_204_NO_CONTENT,
)

search.__doc__ = v1_search.__doc__
get.__doc__ = v1_get.__doc__
