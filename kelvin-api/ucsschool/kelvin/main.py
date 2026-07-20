# SPDX-FileCopyrightText: 2020-2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

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
from .routers import v1, v2
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


@app.get("/health", include_in_schema=False)
async def health(_: None = Depends(check_db_compatibility)):
    return {"status": "ok"}


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
    sub_data = user.dict(include={"username", "kelvin_admin", "kelvin_reader"})
    sub_data["schools"] = user.attributes.get("ucsschoolSchool", [])
    sub_data["roles"] = user.attributes.get("ucsschoolRole", [])
    access_token = await create_access_token(data={"sub": sub_data}, expires_delta=access_token_expires)
    logger.debug("User %r retrieved access_token.", user.username)
    return {"access_token": access_token, "token_type": "bearer"}


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


v1_router = APIRouter(prefix=URL_API_V1_PREFIX)
v2_router = APIRouter(prefix=URL_API_V2_PREFIX, dependencies=[Depends(check_db_compatibility)])

v1_router.include_router(
    v1.school_class.router,
    prefix="/classes",
    tags=["classes"],
)
v1_router.include_router(
    v1.workgroup.router,
    prefix="/workgroups",
    tags=["workgroups"],
)
v1_router.include_router(
    v1.role.router,
    prefix="/roles",
    tags=["roles"],
)
v1_router.include_router(
    v1.school.router,
    prefix="/schools",
    tags=["schools"],
)
v1_router.include_router(
    v1.user.router,
    prefix="/users",
    tags=["users"],
)
v1_router.include_router(v1.doc.router)

v2_router.include_router(
    v2.school_class.router,
    prefix="/classes",
    tags=["classes"],
)
v2_router.include_router(
    v2.workgroup.router,
    prefix="/workgroups",
    tags=["workgroups"],
)
v2_router.include_router(
    v2.role.router,
    prefix="/roles",
    tags=["roles"],
)
v2_router.include_router(
    v2.school.router,
    prefix="/schools",
    tags=["schools"],
)
v2_router.include_router(
    v2.user.router,
    prefix="/users",
    tags=["users"],
)
v2_router.include_router(v1.doc.router)


app.include_router(v1_router)
app.include_router(v2_router)
app.include_router(v1.doc.service_router)
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
