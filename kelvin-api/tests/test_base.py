# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import pytest
from requests import Request

from ucsschool.kelvin.routers.v1.base import udm_ctx

pytestmark = pytest.mark.in_container


@pytest.mark.asyncio
@pytest.mark.parametrize("language", [None, "de", "en", "de-DE", "en-US;q=0.95"])
async def test_udm_ctx(language):
    request = Request()
    request.headers = {"Accept-Language": language} if language else {}
    udm = await udm_ctx(request).__anext__()
    assert udm.session.language == language
