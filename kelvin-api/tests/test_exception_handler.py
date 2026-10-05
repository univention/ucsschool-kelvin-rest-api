# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from ucsschool.kelvin.service.exception_handler import add_exception_handlers


class Login(BaseModel):
    name: str
    password: str


def test_a_validation_error_does_not_echo_the_request_body():
    app = FastAPI()
    add_exception_handlers(app, MagicMock())

    @app.post("/login")
    async def login(body: Login) -> None: ...

    response = TestClient(app).post("/login", json={"password": "s3cr3t"})

    assert response.status_code == 422
    assert response.json() == {
        "detail": [{"type": "missing", "loc": ["body", "name"], "msg": "Field required"}]
    }
