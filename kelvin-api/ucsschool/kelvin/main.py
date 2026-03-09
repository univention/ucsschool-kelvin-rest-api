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
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse, ORJSONResponse, RedirectResponse
from fastapi.routing import APIRoute
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
    URL_API_V1_PREFIX,
    URL_API_V2_PREFIX,
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
    openapi_url=None,
    default_response_class=ORJSONResponse,
    generate_unique_id_function=unique_operation_id,
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


def _swagger_ui_kwargs(*, static_prefix: str) -> Dict[str, Any]:
    return {
        "title": app.title + " - Swagger UI",
        "oauth2_redirect_url": app.swagger_ui_oauth2_redirect_url,
        "swagger_js_url": f"{static_prefix}/static/swagger-ui-bundle-5.17.14.js",
        "swagger_css_url": f"{static_prefix}/static/swagger-ui-5.17.14.css",
    }


def swagger_ui_html(*, openapi_url: str, static_prefix: str) -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url=openapi_url,
        **_swagger_ui_kwargs(static_prefix=static_prefix),
    )


@app.get(f"{URL_API_V1_PREFIX}/docs", include_in_schema=False)
async def custom_swagger_ui_html_v1():
    return swagger_ui_html(
        openapi_url=f"{URL_API_V1_PREFIX}/openapi.json",
        static_prefix=URL_API_V1_PREFIX,
    )


@app.get(f"{URL_API_V2_PREFIX}/docs", include_in_schema=False)
async def custom_swagger_ui_html_v2():
    return swagger_ui_html(
        openapi_url=f"{URL_API_V2_PREFIX}/openapi.json",
        static_prefix=URL_API_V2_PREFIX,
    )


@app.get(f"{URL_KELVIN_BASE}/docs", include_in_schema=False)
async def custom_service_swagger_ui_html():
    # TODO SwaggerUI supports several API version, which is not yet supported
    #      by FastAPI's `get_swagger_ui_html`. We need to adapt get_swagger_ui_html
    #      see https://github.com/fastapi/fastapi/discussions/14340
    urls = [
        {"url": f"{URL_KELVIN_BASE}/openapi-v1.json", "name": "V1"},
        {"url": f"{URL_KELVIN_BASE}/openapi-v2.json", "name": "V2"},
    ]
    return get_swagger_ui_html(
        openapi_url=urls[0]["url"],
        **_swagger_ui_kwargs(static_prefix=URL_API_V1_PREFIX),
        swagger_ui_parameters={
            "urls": urls,
            "urls.primaryName": urls[0]["name"],
        },
    )


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


def redoc_html_for(*, openapi_url: str, static_prefix: str) -> HTMLResponse:
    return get_redoc_html(
        openapi_url=openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url=f"{static_prefix}/static/redoc.standalone-2.0.0-rc.75.js",
    )


@app.get(f"{URL_API_V1_PREFIX}/redoc", include_in_schema=False)
async def redoc_html_v1():
    return redoc_html_for(
        openapi_url=f"{URL_API_V1_PREFIX}/openapi.json",
        static_prefix=URL_API_V1_PREFIX,
    )


@app.get(f"{URL_API_V2_PREFIX}/redoc", include_in_schema=False)
async def redoc_html_v2():
    return redoc_html_for(
        openapi_url=f"{URL_API_V2_PREFIX}/openapi.json",
        static_prefix=URL_API_V2_PREFIX,
    )


@app.get(f"{URL_KELVIN_BASE}/redoc", include_in_schema=False)
async def redoc_html():
    return redoc_html_for(
        openapi_url=f"{URL_KELVIN_BASE}/openapi-v1.json",
        static_prefix=URL_API_V1_PREFIX,
    )


@app.get(f"{URL_KELVIN_BASE}")
async def docs_redirect():
    return RedirectResponse(url=f"{URL_KELVIN_BASE}/docs")


@app.get(f"{URL_API_V1_PREFIX}/changelog", response_class=HTMLResponse)
async def get_history():
    async with aiofiles.open(STATIC_FILE_CHANGELOG) as fp:
        return await fp.read()


@app.get(f"{URL_API_V2_PREFIX}/changelog", response_class=HTMLResponse)
async def get_history_v2():
    async with aiofiles.open(STATIC_FILE_CHANGELOG) as fp:
        return await fp.read()


@app.get(f"{URL_API_V1_PREFIX}/readme", response_class=HTMLResponse)
async def get_readme():
    async with aiofiles.open(STATIC_FILE_README) as fp:
        return await fp.read()


@app.get(f"{URL_API_V2_PREFIX}/readme", response_class=HTMLResponse)
async def get_readme_v2():
    async with aiofiles.open(STATIC_FILE_README) as fp:
        return await fp.read()


def routes_for_prefix(app: FastAPI, prefix: str) -> List[APIRoute]:
    selected_routes: List[APIRoute] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path == prefix or route.path.startswith(f"{prefix}/"):
            selected_routes.append(route)
    return selected_routes


def build_openapi_for_prefix(
    app: FastAPI,
    *,
    prefix: str,
    title: str,
    version: str,
    description: str | None = None,
) -> Dict[str, Any]:
    routes = routes_for_prefix(app, prefix)
    return get_openapi(
        title=title,
        version=version,
        description=description,
        routes=routes,
    )


_openapi_cache: Dict[str, Dict[str, Any]] = {}


def get_versioned_openapi(
    prefix: str, title: str, version: str, description: str | None = None
) -> Dict[str, Any]:
    cache_key = f"{prefix}:{version}"
    if cache_key not in _openapi_cache:
        _openapi_cache[cache_key] = build_openapi_for_prefix(
            app,
            prefix=prefix,
            title=title,
            version=version,
            description=description,
        )
    return _openapi_cache[cache_key]


@app.get(f"{URL_KELVIN_BASE}/openapi-v1.json", include_in_schema=False)
@app.get(f"{URL_API_V1_PREFIX}/openapi.json", include_in_schema=False)
def openapi_v1():
    return JSONResponse(
        get_versioned_openapi(
            prefix=URL_API_V1_PREFIX,
            title=f"{app.title} - V1",
            version=str(APP_VERSION),
            description=app.description,
        )
    )


@app.get(f"{URL_KELVIN_BASE}/openapi-v2.json", include_in_schema=False)
@app.get(f"{URL_API_V2_PREFIX}/openapi.json", include_in_schema=False)
def openapi_v2():
    return JSONResponse(
        get_versioned_openapi(
            prefix=URL_API_V2_PREFIX,
            title=f"{app.title} - V2",
            version=str(APP_VERSION),
            description=app.description,
        )
    )


v1 = APIRouter(prefix=URL_API_V1_PREFIX)
v2 = APIRouter(prefix=URL_API_V2_PREFIX)

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


app.include_router(v1)
app.include_router(v2)
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


@app.on_event("startup")
def log_version():  # should be the last 'startup' event function
    logger = logging.getLogger(__name__)
    logger.info(f"Started {app.title} version {app.version}.")
