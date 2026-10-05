# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import logging
import time

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from starlette.routing import BaseRoute, Match, Mount, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

METRIC_PREFIX = "kelvin_app"


class TimingMiddleware:
    """Log the wall and CPU time of each HTTP request, named after the route that handled it."""

    def __init__(self, app: ASGIApp, logger: logging.Logger, routes: list[BaseRoute]) -> None:
        self.app = app
        self._logger = logger
        self._routes = routes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        mount = next(
            (r for r in self._routes if isinstance(r, Mount) and r.matches(scope)[0] == Match.FULL), None
        )
        status: int | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        wall, cpu = time.perf_counter(), time.process_time()
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status = 500
            raise
        finally:
            # FastAPI >= 0.142 resolves nested routes only while handling the request.
            name = self._metric_name(scope, mount)
            tags = [f"http_status:{status}", f"http_method:{scope['method']}"]
            self._log(name, time.perf_counter() - wall, [*tags, "time:wall"])
            self._log(name, time.process_time() - cpu, [*tags, "time:cpu"])

    @staticmethod
    def _metric_name(scope: Scope, mount: Mount | None) -> str:
        route = scope.get("route")
        if isinstance(route, Route):
            return f"{METRIC_PREFIX}.{route.endpoint.__module__}.{route.name}"
        if mount is not None:
            return f"{METRIC_PREFIX}.__mount__.{mount.name}"
        path: str = scope["path"]
        return f"{METRIC_PREFIX}.{path[1:].replace('/', '.')}"

    def _log(self, name: str, seconds: float, tags: list[str]) -> None:
        log = self._logger.debug if name.endswith(".health") else self._logger.warning
        log(f"{name} - {seconds:.3f} s - {tags}")


def add_middlewares(app: FastAPI, logger: logging.Logger) -> None:
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(TimingMiddleware, logger=logger, routes=app.router.routes)
