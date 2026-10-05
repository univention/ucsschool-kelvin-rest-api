# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from unittest.mock import MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from ucsschool.kelvin.service.middleware import add_middlewares


@pytest.mark.parametrize(
    "path, metric_name",
    [
        ("/v1/users/alice", f"kelvin_app.{__name__}.get"),
        ("/v1/static/x.css", "kelvin_app.__mount__.static"),
        ("/v1/nowhere", "kelvin_app.v1.nowhere"),
    ],
)
def test_the_timing_metric_is_named_after_the_route(path: str, metric_name: str):
    users = APIRouter()

    @users.get("/{username}", name="get")
    async def user_get(username: str) -> dict[str, str]:
        return {"username": username}

    v1 = APIRouter(prefix="/v1")
    v1.include_router(users, prefix="/users")
    app = FastAPI()
    logger = MagicMock()
    add_middlewares(app, logger)
    app.include_router(v1)
    app.mount("/v1/static", PlainTextResponse("css"), name="static")

    _ = TestClient(app).get(path)

    assert {call.args[0].split(" - ")[0] for call in logger.warning.call_args_list} == {metric_name}
