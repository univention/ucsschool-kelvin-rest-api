import re
from typing import Any, Dict, List

import aiofiles
from fastapi import APIRouter, FastAPI, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.routing import APIRoute

from ..constants import (
    APP_VERSION,
    STATIC_FILE_CHANGELOG,
    STATIC_FILE_README,
    URL_API_V1_PREFIX,
    URL_API_V2_PREFIX,
    URL_KELVIN_BASE,
)
from .fastapi_doc_patch import get_swagger_ui_html as patched_get_swagger_ui_html

router = APIRouter()
service_router = APIRouter(prefix=URL_KELVIN_BASE)


def _is_v2_path(path: str) -> bool:
    return bool(re.match(rf"^{URL_API_V2_PREFIX}(?:/|$)", path))


def _versioned_api_prefix(path: str) -> str:
    return URL_API_V2_PREFIX if _is_v2_path(path) else URL_API_V1_PREFIX


def _swagger_ui_kwargs(*, request: Request, static_prefix: str) -> Dict[str, Any]:
    return {
        "title": request.app.title + " - Swagger UI",
        "oauth2_redirect_url": request.app.swagger_ui_oauth2_redirect_url,
        "swagger_js_url": f"{static_prefix}/static/swagger-ui-bundle-5.17.14.js",
        "swagger_css_url": f"{static_prefix}/static/swagger-ui-5.17.14.css",
    }


def _redoc_html_for(*, request: Request, openapi_url: str, static_prefix: str) -> HTMLResponse:
    return get_redoc_html(
        openapi_url=openapi_url,
        title=request.app.title + " - ReDoc",
        redoc_js_url=f"{static_prefix}/static/redoc.standalone-2.0.0-rc.75.js",
    )


def _routes_for_prefix(app: FastAPI, prefix: str) -> List[APIRoute]:
    selected_routes: List[APIRoute] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path == prefix or route.path.startswith(f"{prefix}/"):
            selected_routes.append(route)
    return selected_routes


def _build_openapi_for_prefix(
    app: FastAPI,
    *,
    prefix: str,
    title: str,
    version: str,
    description: str | None = None,
) -> Dict[str, Any]:
    routes = _routes_for_prefix(app, prefix)
    return get_openapi(
        title=title,
        version=version,
        description=description,
        routes=routes,
    )


_openapi_cache: Dict[str, Dict[str, Any]] = {}


def _get_versioned_openapi(
    app: FastAPI, prefix: str, title: str, version: str, description: str | None = None
) -> Dict[str, Any]:
    cache_key = f"{prefix}:{version}"
    if cache_key not in _openapi_cache:
        _openapi_cache[cache_key] = _build_openapi_for_prefix(
            app,
            prefix=prefix,
            title=title,
            version=version,
            description=description,
        )
    return _openapi_cache[cache_key]


@router.get("/docs", include_in_schema=False)
async def swagger_ui_html_versioned(request: Request) -> HTMLResponse:
    prefix = _versioned_api_prefix(request.url.path)
    return get_swagger_ui_html(
        openapi_url=f"{prefix}/openapi.json",
        **_swagger_ui_kwargs(request=request, static_prefix=prefix),
    )


@service_router.get("/docs", include_in_schema=False)
async def swagger_ui_html_service(request: Request) -> HTMLResponse:
    urls = [
        {"url": f"{URL_KELVIN_BASE}/openapi-v1.json", "name": "V1"},
        {"url": f"{URL_KELVIN_BASE}/openapi-v2.json", "name": "V2"},
    ]
    return patched_get_swagger_ui_html(
        openapi_urls=urls,
        **_swagger_ui_kwargs(request=request, static_prefix=URL_API_V1_PREFIX),
        swagger_ui_parameters={
            "urls": urls,
            "urls.primaryName": urls[0]["name"],
            "layout": "StandaloneLayout",
        },
    )


@router.get("/redoc", include_in_schema=False)
async def redoc_html_versioned(request: Request) -> HTMLResponse:
    prefix = _versioned_api_prefix(request.url.path)
    return _redoc_html_for(
        request=request,
        openapi_url=f"{prefix}/openapi.json",
        static_prefix=prefix,
    )


@service_router.get("/redoc", include_in_schema=False)
async def redoc_html_service(request: Request) -> HTMLResponse:
    return _redoc_html_for(
        request=request,
        openapi_url=f"{URL_KELVIN_BASE}/openapi-v1.json",
        static_prefix=URL_API_V1_PREFIX,
    )


@service_router.get("")
async def docs_redirect() -> RedirectResponse:
    return RedirectResponse(url=f"{URL_KELVIN_BASE}/docs")


@router.get("/changelog", response_class=HTMLResponse)
async def get_history() -> str:
    async with aiofiles.open(STATIC_FILE_CHANGELOG) as fp:
        return await fp.read()


@router.get("/readme", response_class=HTMLResponse)
async def get_readme() -> str:
    async with aiofiles.open(STATIC_FILE_README) as fp:
        return await fp.read()


@router.get("/openapi.json", include_in_schema=False)
def openapi_versioned(request: Request) -> JSONResponse:
    prefix = _versioned_api_prefix(request.url.path)
    title_suffix = "V2" if prefix == URL_API_V2_PREFIX else "V1"
    return JSONResponse(
        _get_versioned_openapi(
            request.app,
            prefix=prefix,
            title=f"{request.app.title} - {title_suffix}",
            version=str(APP_VERSION),
            description=request.app.description,
        )
    )


@service_router.get("/openapi-v1.json", include_in_schema=False)
def openapi_v1(request: Request) -> JSONResponse:
    return JSONResponse(
        _get_versioned_openapi(
            request.app,
            prefix=URL_API_V1_PREFIX,
            title=f"{request.app.title} - V1",
            version=str(APP_VERSION),
            description=request.app.description,
        )
    )


@service_router.get("/openapi-v2.json", include_in_schema=False)
def openapi_v2(request: Request) -> JSONResponse:
    return JSONResponse(
        _get_versioned_openapi(
            request.app,
            prefix=URL_API_V2_PREFIX,
            title=f"{request.app.title} - V2",
            version=str(APP_VERSION),
            description=request.app.description,
        )
    )
