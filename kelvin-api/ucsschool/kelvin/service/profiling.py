# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import asyncio
import datetime
import logging
import os
import re
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute
from pyinstrument import Profiler
from pyinstrument.session import Session
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.routing import Match
from starlette.types import ASGIApp
from typing_extensions import override

from ..constants import URL_KELVIN_BASE

PROFILE_HEADER = "X-Kelvin-Profile"
PROFILE_FILE_HEADER = "X-Kelvin-Profile-File"
CORRELATION_ID_HEADER = "X-Request-ID"
DEFAULT_INTERVAL = 0.001

_UNSAFE_IN_FILENAME = re.compile(r"[^A-Za-z0-9]+")


def _is_api_request(app: FastAPI, request: Request) -> bool:
    """
    Whether `request` addresses an endpoint of the API itself, rather than the static
    files, the documentation or the health check.

    An endpoint qualifies by being a route that appears in an OpenAPI document and does
    not answer with a rendered HTML document. The mounted static directories are not
    routes at all; the Swagger UI, ReDoc, the OpenAPI documents and `/health` are kept
    out of the documents; and the changelog and readme routes, while documented, serve
    documentation as HTML. Only the redirect from the API's base URL to the Swagger UI
    passes all of that and has to be named.
    """
    for route in app.router.routes:
        if route.matches(request.scope)[0] != Match.FULL:
            continue
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            return False
        if route.path == URL_KELVIN_BASE:
            return False
        response_class = route.response_class
        return not (isinstance(response_class, type) and issubclass(response_class, HTMLResponse))
    return False


def _interval_from_env(logger: logging.Logger) -> float:
    raw = os.environ.get("KELVIN_PROFILE_INTERVAL", "").strip()
    if not raw:
        return DEFAULT_INTERVAL
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "Ignoring KELVIN_PROFILE_INTERVAL=%r, not a number. Using %s s.", raw, DEFAULT_INTERVAL
        )
        return DEFAULT_INTERVAL


class ProfilingMiddleware(BaseHTTPMiddleware):
    """
    Requests carrying the `X-Kelvin-Profile` header are answered with the pyinstrument
    report as HTML, instead of their own response body. All others are answered normally
    and their profile is written to `output_dir` as a `.pyisession` file, to be rendered
    later with `pyinstrument --load <file> -r <html|speedscope|text>`.
    """

    _fastapi_app: FastAPI
    _output_dir: Path
    _logger: logging.Logger
    _interval: float
    _lock: asyncio.Lock

    def __init__(
        self,
        app: ASGIApp,
        *,
        fastapi_app: FastAPI,
        output_dir: Path,
        logger: logging.Logger,
    ) -> None:
        super().__init__(app)
        self._fastapi_app = fastapi_app
        self._output_dir = output_dir
        self._logger = logger
        self._interval = _interval_from_env(logger)
        # pyinstrument refuses a second profiler in the same async context, and
        # 'async_mode="disabled"' would interleave event loop frames into every report.
        self._lock = asyncio.Lock()

    @override
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not _is_api_request(self._fastapi_app, request):
            return await call_next(request)
        async with self._lock:
            profiler = Profiler(interval=self._interval, async_mode="enabled")
            profiler.start()
            try:
                response = await call_next(request)
            finally:
                session = profiler.stop()
            if PROFILE_HEADER in request.headers:
                return HTMLResponse(profiler.output_html())
            self._save(session, request, response)
            return response

    def _save(self, session: Session, request: Request, response: Response) -> None:
        path = self._output_dir / self._file_name(request, response)
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            session.save(path)
        except OSError:
            self._logger.exception("Could not write profile to %s.", path)
            return
        response.headers[PROFILE_FILE_HEADER] = path.name
        self._logger.warning("Wrote profile of %s %s to %s.", request.method, request.url.path, path)

    def _file_name(self, request: Request, response: Response) -> str:
        parts = [
            datetime.datetime.now().strftime("%Y%m%d-%H%M%S.%f"),
            request.method,
            _UNSAFE_IN_FILENAME.sub("_", request.url.path).strip("_") or "root",
            response.headers.get(CORRELATION_ID_HEADER, "no-correlation-id"),
        ]
        return f"{'-'.join(parts)}.pyisession"


def add_profiling_middleware(app: FastAPI, output_dir: Path, logger: logging.Logger) -> None:
    app.add_middleware(ProfilingMiddleware, fastapi_app=app, output_dir=output_dir, logger=logger)
    logger.warning("Profiling is enabled, writing to %s. This slows down every request.", output_dir)
