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
from typing import Any, Dict, List

import aiofiles
from asgi_correlation_id import CorrelationIdMiddleware
from asgi_correlation_id.context import correlation_id
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.responses import HTMLResponse, JSONResponse, ORJSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from starlette.routing import Match, Mount, Route
from timing_asgi import TimingClient, TimingMiddleware
from timing_asgi.integrations import StarletteScopeToName

from ucsschool.lib.models.attributes import ValidationError as SchooLibValidationError
from ucsschool.lib.models.base import NoObject
from ucsschool.lib.models.utils import env_or_ucr, get_stdout_handler
from ucsschool.lib.models.validator import VALIDATION_LOGGER
from udm_rest_client import UdmError

from .config import UDM_MAPPING_CONFIG, load_configurations
from .constants import (
    APP_VERSION,
    DEFAULT_LOG_LEVELS,
    STATIC_FILE_CHANGELOG,
    STATIC_FILE_README,
    STATIC_FILES_PATH,
    URL_API_PREFIX,
    URL_KELVIN_BASE,
    URL_TOKEN_BASE,
)
from .import_config import get_import_config
from .ldap import check_auth_and_get_user
from .routers import role, school, school_class, user, workgroup
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
app.add_middleware(CorrelationIdMiddleware)
logger = get_logger()


class PrintTimings(TimingClient):
    def timing(self, metric_name, timing, tags):
        logger.warning(f"{metric_name} - {timing:.3f} s - {tags}")


class StarletteScopeToNamePatched(StarletteScopeToName):
    """
    timing-asgi throws an error for Mounts

    This is hopefully just a temporary fix:
    https://github.com/steinnes/timing-asgi/issues/27
    """

    def __call__(self, scope):
        route = None
        for r in self.starlette_app.router.routes:
            if r.matches(scope)[0] == Match.FULL:
                route = r
                break
        if isinstance(route, Route):
            return f"{self.prefix}.{route.endpoint.__module__}.{route.name}"
        elif isinstance(route, Mount):
            return f"{self.prefix}.__mount__.{route.name}"
        else:
            return self.fallback(scope)


app.add_middleware(
    TimingMiddleware,
    client=PrintTimings(),
    metric_namer=StarletteScopeToNamePatched(prefix="kelvin_app", starlette_app=app),
)


class ValidationDataFilter(logging.Filter):
    def filter(self, record):
        return record.name != VALIDATION_LOGGER


@app.on_event("startup")
def setup_logging() -> None:
    min_level = env_or_ucr("ucsschool/kelvin/log_level")
    if min_level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        min_level = logging.ERROR
    min_level = logging._checkLevel(min_level)
    abs_min_level = min_level
    for name, default_level in DEFAULT_LOG_LEVELS.items():
        logger = logging.getLogger(name)
        logger.setLevel(min(default_level, min_level))
        abs_min_level = min(abs_min_level, logger.level)

    file_handler = get_stdout_handler(abs_min_level)
    file_handler.addFilter(ValidationDataFilter())
    logger = logging.getLogger("uvicorn.access")
    logger.addHandler(file_handler)
    logger = logging.getLogger()
    logger.setLevel(abs_min_level)
    logger.addHandler(file_handler)


@app.exception_handler(UdmError)
async def udm_exception_handler(request: Request, exc: UdmError) -> ORJSONResponse:
    """Format unhandled udm exceptions and return in a standard JSON format"""

    error_type = f"UdmError:{exc.__class__.__name__}"
    errors: List[Dict[str, Any]]
    if exc.error is not None:
        errors = [
            {"loc": (location,), "msg": message, "type": error_type}
            for (location, message) in exc.error.items()
        ]
    elif exc.reason is not None:
        errors = [{"loc": (), "msg": exc.reason, "type": error_type}]
    else:
        errors = [{"loc": (), "msg": str(exc), "type": error_type}]

    status_code = exc.status or 500

    logger.error(f"Encountered exception {exc} responding with {errors}")

    return ORJSONResponse(
        content=jsonable_encoder({"detail": errors}),
        status_code=status_code,
        headers={
            CorrelationIdMiddleware.header_name: correlation_id.get() or "",
            "Access-Control-Expose-Headers": CorrelationIdMiddleware.header_name,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Add Correlation-ID to HTTP 500."""
    logger.exception(f"While responding to {request.method!s} {request.url!s}: {exc!s}")
    return await http_exception_handler(
        request,
        HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal server error",
            headers={
                CorrelationIdMiddleware.header_name: correlation_id.get() or "",
                "Access-Control-Expose-Headers": CorrelationIdMiddleware.header_name,
            },
        ),
    )


@app.on_event("startup")
def load_configs():
    load_configurations()
    logger: logging.Logger = get_logger()
    logger.info("UDM mapping configuration: %s", UDM_MAPPING_CONFIG)


@app.on_event("startup")
def configure_import():
    get_import_config()


@app.exception_handler(NoObject)
async def no_object_exception_handler(request: Request, exc: NoObject):
    return ORJSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": str(exc)})


@app.exception_handler(SchooLibValidationError)
async def school_lib_validation_exception_handler(request: Request, exc: SchooLibValidationError):
    return ORJSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"message": str(exc)})


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


@app.on_event("startup")
def log_version():  # should be the last 'startup' event function
    logger = logging.getLogger(__name__)
    logger.info(f"Started {app.title} version {app.version}.")
