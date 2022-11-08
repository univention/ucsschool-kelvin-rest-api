import pytest
from requests import Request

from ucsschool.kelvin.routers.base import udm_ctx


@pytest.mark.asyncio
@pytest.mark.parametrize("language", [None, "de", "en", "de-DE", "en-US;q=0.95"])
async def test_udm_ctx(language):
    request = Request()
    request.headers = {"Accept-Language": language} if language else {}
    udm = await udm_ctx(request).__anext__()
    assert udm.session.language == language
