# SPDX-FileCopyrightText: 2024 - 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import pytest
from fastapi.testclient import TestClient

from ucsschool.kelvin.constants import URL_KELVIN_BASE
from ucsschool.kelvin.main import app


@pytest.mark.asyncio
async def test_get_root():
    client = TestClient(app, base_url="http://test.server")
    response = client.get(URL_KELVIN_BASE)
    assert response.url.path == f"{URL_KELVIN_BASE}/docs"
