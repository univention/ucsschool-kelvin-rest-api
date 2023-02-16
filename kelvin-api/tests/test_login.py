import pytest
import requests

import ucsschool.kelvin.constants
from ucsschool.lib.models.user import User

pytestmark = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)


def removesuffix(input_string, suffix):
    if suffix and input_string.endswith(suffix):
        return input_string[: -len(suffix)]
    return input_string


@pytest.mark.asyncio
async def test_login(retry_http_502, url_fragment, create_ou_using_python, new_school_user):
    password: str = "testpassword"
    school = await create_ou_using_python()
    user: User = await new_school_user(school, "staff", password=password)
    login_url = f"{removesuffix(url_fragment, '/v1')}/token"
    # login with the wrong password -> 401
    response1 = retry_http_502(
        requests.post,
        login_url,
        data={"username": user.name, "password": "wrongpassword"},
    )
    assert response1.status_code == 401
    # login with the right password -> 200
    response2 = retry_http_502(
        requests.post, login_url, data={"username": user.name, "password": password}
    )
    assert response2.status_code == 200
    # login with the wrong password even if there's a cached session with the right one -> 401
    response3 = retry_http_502(
        requests.post,
        login_url,
        data={"username": user.name, "password": "wrongpassword"},
    )
    assert response3.status_code == 401

@pytest.mark.asyncio
async def test_login_default_admin(retry_http_502, url_fragment):
    """like test_login, but dedicated to the default Administrator"""

    login_url = f"{removesuffix(url_fragment, '/v1')}/token"
    # login with the right password -> 200
    response1 = retry_http_502(
        requests.post, login_url, data={"username": "Administrator", "password": "univention"}
    )
    assert response1.status_code == 200

    # login with the wrong password
    response2 = retry_http_502(
        requests.post,
        login_url,
        data={"username": "Administrator", "password": "wrongpassword"},
    )
    assert response2.status_code == 401

    # login with no password
    response2 = retry_http_502(
        requests.post,
        login_url,
        data={"username": "Administrator", "password": ""},
    )
    assert response2.status_code == 401
