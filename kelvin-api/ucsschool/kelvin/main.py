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
from datetime import timedelta
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.openapi.docs import get_swagger_ui_oauth2_redirect_html
from fastapi.responses import ORJSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles

from .constants import (
    APP_VERSION,
    STATIC_FILES_PATH,
    URL_API_V1_PREFIX,
    URL_API_V2_PREFIX,
    URL_TOKEN_BASE,
)
from .ldap import check_auth_and_get_user
from .routers import doc, role, school, school_class, user, workgroup
from .service.dependency import check_db_compatibility
from .service.exception_handler import add_exception_handlers
from .service.lifespan import build_app_lifespan
from .service.middleware import add_middlewares
from .token_auth import Token, create_access_token, get_token_ttl


@lru_cache(maxsize=1)
def get_logger() -> logging.Logger:
    return logging.getLogger(__name__)


logger = get_logger()


def unique_operation_id(route: Any) -> str:
    methods = "_".join(sorted(getattr(route, "methods", []) or []))
    route_name = getattr(route, "name", None) or "route"
    path = getattr(route, "path_format", "")
    normalized_path = path.replace("/", "_").replace("{", "").replace("}", "").strip("_")
    return f"{route_name}_{normalized_path}_{methods}".lower()


app = FastAPI(
    title="Kelvin API",
    description="UCS@school Kelvin REST API",
    version=str(APP_VERSION),
    docs_url=None,
    redoc_url=None,
    lifespan=build_app_lifespan(logger),
    openapi_url=None,
    default_response_class=ORJSONResponse,
    generate_unique_id_function=unique_operation_id,
)
add_middlewares(app, logger)
add_exception_handlers(app, logger)


@app.post(URL_TOKEN_BASE, response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    logger: logging.Logger = Depends(get_logger),
):
    user = check_auth_and_get_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    access_token_expires = timedelta(minutes=get_token_ttl())
    sub_data = user.dict(include={"username", "kelvin_admin"})
    sub_data["schools"] = user.attributes.get("ucsschoolSchool", [])
    sub_data["roles"] = user.attributes.get("ucsschoolRole", [])
    access_token = await create_access_token(data={"sub": sub_data}, expires_delta=access_token_expires)
    logger.debug("User %r retrieved access_token.", user.username)
    return {"access_token": access_token, "token_type": "bearer"}


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


v1 = APIRouter(prefix=URL_API_V1_PREFIX)
v2 = APIRouter(prefix=URL_API_V2_PREFIX, dependencies=[Depends(check_db_compatibility)])

v1.include_router(
    school_class.router,
    prefix="/classes",
    tags=["classes"],
)
v1.include_router(
    workgroup.router,
    prefix="/workgroups",
    tags=["workgroups"],
)
v1.include_router(
    role.router,
    prefix="/roles",
    tags=["roles"],
)
v1.include_router(
    school.router,
    prefix="/schools",
    tags=["schools"],
)
v1.include_router(
    user.router,
    prefix="/users",
    tags=["users"],
)
v1.include_router(doc.router)

v2.include_router(
    school_class.router,
    prefix="/classes",
    tags=["classes"],
)
v2.include_router(
    workgroup.router,
    prefix="/workgroups",
    tags=["workgroups"],
)
v2.include_router(
    role.router,
    prefix="/roles",
    tags=["roles"],
)
v2.include_router(
    school.router,
    prefix="/schools",
    tags=["schools"],
)
v2.include_router(
    user.router,
    prefix="/users",
    tags=["users"],
)
v2.include_router(doc.router)


app.include_router(v1)
app.include_router(v2)
app.include_router(doc.service_router)
app.mount(
    f"{URL_API_V1_PREFIX}/static",
    StaticFiles(directory=str(STATIC_FILES_PATH)),
    name="static",
)
app.mount(
    f"{URL_API_V2_PREFIX}/static",
    StaticFiles(directory=str(STATIC_FILES_PATH)),
    name="static_v2",
)
