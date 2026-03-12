# Copyright 2026 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient
from starlette.routing import NoMatchFound

from ucsschool.kelvin.urls import cached_url_for, url_to_name
from ucsschool.lib.models.base import NoObject


@pytest.fixture
def test_app() -> FastAPI:
    item_router = APIRouter()
    object_router = APIRouter()

    @item_router.get("/{item_id}", name="item_get")
    async def get_item(request: Request, item_id: str):
        return {"resolved_url": str(cached_url_for(request, "item_get", item_id=item_id))}

    @object_router.get("/schools/{school_name}", name="school_get")
    async def school_get(school_name: str):
        return {"school_name": school_name}

    @object_router.get("/users/{username}", name="get")
    async def user_get(username: str):
        return {"username": username}

    @object_router.get("/roles/{role_name}", name="get")
    async def role_get(role_name: str):
        return {"role_name": role_name}

    @object_router.get("/_test/url_to_name/{obj_type}")
    async def test_url_to_name(request: Request, obj_type: str, url: str | None = None):
        return {"url_to_name": url_to_name(request, obj_type, url)}

    @object_router.get("/_test/no_match")
    async def test_no_match(request: Request):
        return {"resolved_url": str(cached_url_for(request, "does_not_exist"))}

    app = FastAPI()
    v1 = APIRouter(prefix="/v1")
    v2 = APIRouter(prefix="/v2")
    v1.include_router(item_router, prefix="/items")
    v2.include_router(item_router, prefix="/items")
    v1.include_router(object_router)
    v2.include_router(object_router)
    app.include_router(v1)
    app.include_router(v2)

    return app


@pytest.fixture
def test_client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app, base_url="http://kelvin.server.test")


@pytest.fixture(autouse=True)
def clear_cached_url_for_cache():
    cached_url_for.cache.clear()
    url_to_name.cache.clear()


@pytest.mark.parametrize(
    "query, expected_url",
    [
        pytest.param("v1/items/demo", "http://kelvin.server.test/v1/items/demo", id="v1"),
        pytest.param("v2/items/demo", "http://kelvin.server.test/v2/items/demo", id="v2"),
    ],
)
def test_cached_url_should_vary_by_api_version(test_client: TestClient, query: str, expected_url: str):
    response = test_client.get(query)

    assert response.status_code == 200
    assert response.json()["resolved_url"] == expected_url


def test_cached_url_for_raises_no_match_found(test_client: TestClient):
    with pytest.raises(NoMatchFound):
        test_client.get("/v1/_test/no_match")


@pytest.mark.parametrize(
    "request_path, obj_type, url, expected",
    [
        pytest.param(
            "/v1/schools/DEMOSCHOOL",
            "school",
            "http://kelvin.server.test/v1/schools/DEMOSCHOOL",
            "DEMOSCHOOL",
            id="school-v1",
        ),
        pytest.param(
            "/v2/users/demo_student",
            "user",
            "http://kelvin.server.test/v2/users/demo_student",
            "demo_student",
            id="user-v2",
        ),
    ],
)
def test_url_to_name_happy_paths(
    test_client: TestClient,
    request_path: str,
    obj_type: str,
    url: str,
    expected: str,
):
    api_prefix = request_path.split("/")[1]
    response = test_client.get(f"/{api_prefix}/_test/url_to_name/{obj_type}", params={"url": url})

    assert response.status_code == 200
    assert response.json() == {"url_to_name": expected}


@pytest.mark.parametrize(
    "request_path, obj_type, url, expected",
    [
        pytest.param("/v1/schools/DEMOSCHOOL", "school", "", "", id="empty-string-url"),
        pytest.param("/v1/schools/DEMOSCHOOL", "school", None, None, id="none-url"),
    ],
)
def test_url_to_name_returns_falsy_url_unchanged(
    test_client: TestClient,
    request_path: str,
    obj_type: str,
    url,
    expected,
):
    api_prefix = request_path.split("/")[1]
    params = {} if url is None else {"url": url}
    response = test_client.get(f"/{api_prefix}/_test/url_to_name/{obj_type}", params=params)

    assert response.status_code == 200
    assert response.json() == {"url_to_name": expected}


@pytest.mark.parametrize(
    "request_path, obj_type, url, expected_exception",
    [
        pytest.param(
            "/v1/schools/DEMOSCHOOL",
            "school",
            "https://kelvin.server.test/v1/schools/DEMOSCHOOL",
            RuntimeError,
            id="https-url",
        ),
        pytest.param(
            "/v1/schools/DEMOSCHOOL",
            "unsupported",
            "http://kelvin.server.test/v1/schools/DEMOSCHOOL",
            NoObject,
            id="unsupported-obj-type",
        ),
        pytest.param(
            "/v1/schools/DEMOSCHOOL",
            "school",
            "http://kelvin.server.test/v2/schools/DEMOSCHOOL",
            NoObject,
            id="api-prefix-mismatch",
        ),
        pytest.param(
            "/v1/users/demo_student",
            "user",
            "http://kelvin.server.test/v1/users/demo_student/",
            NoObject,
            id="trailing-slash-mismatch",
        ),
    ],
)
def test_url_to_name_raises_expected_exceptions(
    test_client: TestClient,
    request_path: str,
    obj_type: str,
    url: str,
    expected_exception,
):
    api_prefix = request_path.split("/")[1]

    with pytest.raises(expected_exception):
        test_client.get(f"/{api_prefix}/_test/url_to_name/{obj_type}", params={"url": url})


def test_url_to_name_uses_cache_for_identical_calls(test_client: TestClient):
    url = "http://kelvin.server.test/v1/schools/DEMOSCHOOL"

    first_response = test_client.get("/v1/_test/url_to_name/school", params={"url": url})
    second_response = test_client.get("/v1/_test/url_to_name/school", params={"url": url})

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json() == {"url_to_name": "DEMOSCHOOL"}
    assert second_response.json() == {"url_to_name": "DEMOSCHOOL"}
    assert len(url_to_name.cache) == 1


def test_url_to_name_cache_key_separates_by_object_type(test_client: TestClient):
    school_response = test_client.get("/v1/_test/url_to_name/school", params={"url": ""})
    user_response = test_client.get("/v1/_test/url_to_name/user", params={"url": ""})

    assert school_response.status_code == 200
    assert user_response.status_code == 200
    assert school_response.json() == {"url_to_name": ""}
    assert user_response.json() == {"url_to_name": ""}
    assert len(url_to_name.cache) == 2
