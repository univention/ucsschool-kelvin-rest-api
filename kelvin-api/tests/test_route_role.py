# SPDX-FileCopyrightText: 2023 - 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import pytest
import requests
from faker import Faker

import ucsschool.kelvin.constants

pytestmark = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)

fake = Faker()


@pytest.mark.asyncio
@pytest.mark.parametrize("role_name", ["staff", "student", "teacher", "legal_guardian", "school_admin"])
async def test_get_existing_role(auth_header, retry_http_502, url_fragment, role_name):
    response = retry_http_502(
        requests.get,
        f"{url_fragment}/roles/{role_name}",
        headers=auth_header,
    )
    assert response.status_code == 200, response.reason
    assert response.json()["name"] == role_name


@pytest.mark.asyncio
async def test_get_non_existing_role_returns_404(auth_header, retry_http_502, url_fragment):
    response = retry_http_502(
        requests.get,
        f"{url_fragment}/roles/{fake.user_name()}",
        headers=auth_header,
    )
    assert response.status_code == 404, response.reason
