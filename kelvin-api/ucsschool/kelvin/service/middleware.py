import logging
from typing import Any, Dict

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from starlette.routing import Match, Mount, Route
from timing_asgi import TimingClient, TimingMiddleware
from timing_asgi.integrations import StarletteScopeToName


class PrintTimings(TimingClient):
    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def timing(self, metric_name: str, timing: float, tags: Dict[str, Any]) -> None:
        self._logger.warning(f"{metric_name} - {timing:.3f} s - {tags}")


class StarletteScopeToNamePatched(StarletteScopeToName):
    """
    timing-asgi throws an error for Mounts

    This is hopefully just a temporary fix:
    https://github.com/steinnes/timing-asgi/issues/27
    """

    def __call__(self, scope: Dict[str, Any]) -> str:
        route = None
        for r in self.starlette_app.router.routes:
            if r.matches(scope)[0] == Match.FULL:
                route = r
                break
        if isinstance(route, Route):
            return f"{self.prefix}.{route.endpoint.__module__}.{route.name}"
        if isinstance(route, Mount):
            return f"{self.prefix}.__mount__.{route.name}"
        return self.fallback(scope)


def add_middlewares(app: FastAPI, logger: logging.Logger) -> None:
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        TimingMiddleware,
        client=PrintTimings(logger),
        metric_namer=StarletteScopeToNamePatched(prefix="kelvin_app", starlette_app=app),
    )
