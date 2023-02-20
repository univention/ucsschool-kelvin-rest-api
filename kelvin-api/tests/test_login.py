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
    assert "access_token" not in response1.json()
    assert response1.status_code == 401
    # login with the right password -> 200
    response2 = retry_http_502(
        requests.post, login_url, data={"username": user.name, "password": password}
    )
    assert "access_token" in response2.json()
    assert response2.status_code == 200
    # login with the wrong password even if there's a cached session with the right one -> 401
    response3 = retry_http_502(
        requests.post,
        login_url,
        data={"username": user.name, "password": "wrongpassword"},
    )
    assert "access_token" not in response3.json()
    assert response3.status_code == 401


@pytest.mark.asyncio
async def test_login_non_existing_user(retry_http_502, url_fragment):
    login_url = f"{removesuffix(url_fragment, '/v1')}/token"
    # login with non existing user
    response = retry_http_502(
        requests.post,
        login_url,
        data={"username": "DoesNotExists404", "password": "wrongpassword"},
    )
    assert "access_token" not in response.json()
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_empty_password(retry_http_502, url_fragment):
    login_url = f"{removesuffix(url_fragment, '/v1')}/token"
    # login with empty password
    response = retry_http_502(
        requests.post,
        login_url,
        data={"username": "Administrator", "password": ""},
    )
    assert "access_token" not in response.json()
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parameter",
    (
        pytest.param({"username": "Administrator"}, id="existing_user-no_password"),
        pytest.param({"username": "DoesNotExists404"}, id="non_existing_user-no_password"),
        pytest.param({"password": "wrongpassword"}, id="no_user-password"),
        pytest.param({"justSomethingElse": "123"}, id="unrelated_data"),
        pytest.param({}, id="empty_data"),
    ),
)
async def test_login_missing_parameters(parameter: dict, retry_http_502, url_fragment):
    login_url = f"{removesuffix(url_fragment, '/v1')}/token"
    # login with no password
    response = retry_http_502(
        requests.post,
        login_url,
        data=parameter,
    )
    assert "access_token" not in response.json()
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_default_admin(retry_http_502, url_fragment):
    """like test_login, but dedicated to the default Administrator"""

    login_url = f"{removesuffix(url_fragment, '/v1')}/token"
    # login with the right password -> 200
    response1 = retry_http_502(
        requests.post, login_url, data={"username": "Administrator", "password": "univention"}
    )
    assert "access_token" in response1.json()
    assert response1.status_code == 200

    # login with the wrong password
    response2 = retry_http_502(
        requests.post,
        login_url,
        data={"username": "Administrator", "password": "wrongpassword"},
    )
    assert "access_token" not in response2.json()
    assert response2.status_code == 401
