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

import aiofiles
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.responses import HTMLResponse, ORJSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles

from .constants import (
    APP_VERSION,
    STATIC_FILE_CHANGELOG,
    STATIC_FILE_README,
    STATIC_FILES_PATH,
    URL_API_PREFIX,
    URL_KELVIN_BASE,
    URL_TOKEN_BASE,
)
from .ldap import check_auth_and_get_user
from .routers import role, school, school_class, user, workgroup
from .service.event_handler import add_event_handlers
from .service.exception_handler import add_exception_handlers
from .service.middleware import add_middlewares
from .token_auth import Token, create_access_token, get_token_ttl


@lru_cache(maxsize=1)
def get_logger() -> logging.Logger:
    return logging.getLogger(__name__)


app = FastAPI(
    title="Kelvin API",
    description="UCS@school Kelvin REST API",
    version=str(APP_VERSION),
    docs_url=None,
    redoc_url=None,
    openapi_url=f"{URL_API_PREFIX}/openapi.json",
    default_response_class=ORJSONResponse,
)
logger = get_logger()
add_middlewares(app, logger)
add_event_handlers(app, logger)
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


@app.get(f"{URL_API_PREFIX}/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url=f"{URL_API_PREFIX}/static/swagger-ui-bundle-5.17.14.js",
        swagger_css_url=f"{URL_API_PREFIX}/static/swagger-ui-5.17.14.css",
    )


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


@app.get(f"{URL_API_PREFIX}/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url=f"{URL_API_PREFIX}/static/redoc.standalone-2.0.0-rc.75.js",
    )


@app.get(f"{URL_KELVIN_BASE}")
async def docs_redirect():
    return RedirectResponse(url=f"{URL_API_PREFIX}/docs")


@app.get(f"{URL_API_PREFIX}/changelog", response_class=HTMLResponse)
async def get_history():
    async with aiofiles.open(STATIC_FILE_CHANGELOG) as fp:
        return await fp.read()


@app.get(f"{URL_API_PREFIX}/readme", response_class=HTMLResponse)
async def get_readme():
    async with aiofiles.open(STATIC_FILE_README) as fp:
        return await fp.read()


app.include_router(
    school_class.router,
    prefix=f"{URL_API_PREFIX}/classes",
    tags=["classes"],
)
app.include_router(
    workgroup.router,
    prefix=f"{URL_API_PREFIX}/workgroups",
    tags=["workgroups"],
)
# app.include_router(
#     computer_room.router,
#     prefix=f"{URL_API_PREFIX}/computer_rooms",
#     tags=["computer_rooms"],
#     dependencies=[Depends(get_current_active_user)],
# )
# app.include_router(
#     computer_client.router,
#     prefix=f"{URL_API_PREFIX}/computers",
#     tags=["computers"],
#     dependencies=[Depends(get_current_active_user)],
# )
app.include_router(
    role.router,
    prefix=f"{URL_API_PREFIX}/roles",
    tags=["roles"],
)
app.include_router(
    school.router,
    prefix=f"{URL_API_PREFIX}/schools",
    tags=["schools"],
)
# app.include_router(
#     computer_server.router,
#     prefix=f"{URL_API_PREFIX}/servers",
#     tags=["servers"],
#     dependencies=[Depends(get_current_active_user)],
# )
app.include_router(
    user.router,
    prefix=f"{URL_API_PREFIX}/users",
    tags=["users"],
)
app.mount(
    f"{URL_API_PREFIX}/static",
    StaticFiles(directory=str(STATIC_FILES_PATH)),
    name="static",
)
