# Copyright 2020-2021 Univention GmbH
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

import asyncio
import os
import random
import time
from typing import Any, Callable, NamedTuple, Type, Union

import pytest
import requests

import ucsschool.kelvin.constants
from ucsschool.importer.models.import_user import ImportUser
from ucsschool.lib.models.user import (
    LegalGuardian,
    SchoolAdmin,
    Staff,
    Student,
    Teacher,
    TeachersAndStaff,
    User,
)

pytestmark = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)

UserType = Type[Union[Staff, Student, Teacher, TeachersAndStaff, User]]
_Role = NamedTuple("Role", [("name", str), ("klass", UserType)])
USER_ROLES = [
    _Role("staff", Staff),
    _Role("student", Student),
    _Role("teacher", Teacher),
    _Role("legal_guardian", LegalGuardian),
    _Role("teacher_and_staff", TeachersAndStaff),
    _Role("school_admin", SchoolAdmin),
]
ALL_ROLE_NAMES = ["staff", "student", "teacher", "legal_guardian", "school_admin"]


def _make_base_urls() -> tuple[str, str]:
    host = os.environ["DOCKER_HOST_NAME"]
    return (
        f"http://{host}/ucsschool/kelvin/v1",
        f"http://{host}/ucsschool/kelvin/v2",
    )


def normalize_value(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value.replace("/v1/", "/vX/").replace("/v2/", "/vX/")
    if isinstance(value, list):
        return sorted(normalize_value(v) for v in value)
    return value


def assert_responses_equal(v1_data: dict, v2_data: dict) -> None:
    for field, v1_val in v1_data.items():
        v2_val = v2_data.get(field)
        assert normalize_value(v1_val) == normalize_value(
            v2_val
        ), f"{field!r}: v1={v1_val!r} != v2={v2_val!r}"


async def _retry_until_replicated(check: Callable[[], None], timeout: int = 60, interval: int = 2):
    """Repeat a fetch-and-compare until it passes or the deadline expires.

    The v2 cache is replicated asynchronously, so a request can return 200
    with results that do not yet match LDAP — e.g. a search missing a
    just-created object or still listing a just-deleted one. Status-based
    retries (``retry_until_synced``) cannot detect that, so retry on the
    comparison itself and let the last attempt's AssertionError surface.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            check()
            return
        except AssertionError:
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(interval)


def _assert_search_parity(
    v1_response: requests.Response, v2_response: requests.Response, label: str
) -> None:
    assert v1_response.status_code == 200, v1_response.reason
    assert v2_response.status_code == 200, v2_response.reason
    v1_items = {item["name"]: item for item in v1_response.json()}
    v2_items = {item["name"]: item for item in v2_response.json()}
    assert set(v1_items) == set(v2_items), (
        f"{label} sets differ: only in v1={set(v1_items) - set(v2_items)}, "
        f"only in v2={set(v2_items) - set(v1_items)}"
    )
    for name in v1_items:
        assert_responses_equal(v1_items[name], v2_items[name])


# ── Users ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v1_v2_get_user_returns_same_output(
    auth_header,
    retry_http_502,
    create_ou_using_python,
    new_import_user,
    import_config,
):
    """V1 and V2 GET /users/{username} return equivalent data for the same user."""
    role: _Role = random.choice(USER_ROLES)
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, role.name)

    v1_url, v2_url = _make_base_urls()

    def _check() -> None:
        v1_response = retry_http_502(requests.get, f"{v1_url}/users/{user.name}", headers=auth_header)
        assert v1_response.status_code == 200, v1_response.reason
        v2_response = requests.get(f"{v2_url}/users/{user.name}", headers=auth_header)
        assert v2_response.status_code == 200, v2_response.reason
        assert_responses_equal(v1_response.json(), v2_response.json())

    await _retry_until_replicated(_check)


@pytest.mark.asyncio
async def test_v1_v2_search_users_returns_same_output(
    auth_header,
    retry_http_502,
    create_ou_using_python,
    new_school_users,
    import_config,
):
    """V1 and V2 GET /users/?school=… return equivalent data for every user."""
    school = await create_ou_using_python()
    await new_school_users(
        school,
        {"student": 2, "teacher": 2, "staff": 2},
        disabled=False,
    )

    v1_url, v2_url = _make_base_urls()

    def _check() -> None:
        v1_response = retry_http_502(
            requests.get, f"{v1_url}/users/", headers=auth_header, params={"school": school}
        )
        v2_response = requests.get(f"{v2_url}/users/", headers=auth_header, params={"school": school})
        _assert_search_parity(v1_response, v2_response, "User")

    await _retry_until_replicated(_check)


# ── Schools ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v1_v2_get_school_returns_same_output(
    auth_header,
    retry_http_502,
    create_ou_using_python,
):
    """V1 and V2 GET /schools/{name} return equivalent data for the same school."""
    school = await create_ou_using_python()
    v1_url, v2_url = _make_base_urls()

    def _check() -> None:
        v1_response = retry_http_502(requests.get, f"{v1_url}/schools/{school}", headers=auth_header)
        assert v1_response.status_code == 200, v1_response.reason
        v2_response = requests.get(f"{v2_url}/schools/{school}", headers=auth_header)
        assert v2_response.status_code == 200, v2_response.reason
        assert_responses_equal(v1_response.json(), v2_response.json())

    await _retry_until_replicated(_check)


@pytest.mark.asyncio
async def test_v1_v2_search_schools_returns_same_output(
    auth_header,
    retry_http_502,
    create_ou_using_python,
    random_ou_name,
):
    """V1 and V2 GET /schools/?name=… return equivalent data for every matching school."""
    common_name = random_ou_name()
    await create_ou_using_python(ou_name=f"{common_name}a")
    await create_ou_using_python(ou_name=f"{common_name}b")
    v1_url, v2_url = _make_base_urls()

    params = {"name": f"{common_name}*"}

    def _check() -> None:
        v1_response = retry_http_502(
            requests.get, f"{v1_url}/schools/", headers=auth_header, params=params
        )
        v2_response = requests.get(f"{v2_url}/schools/", headers=auth_header, params=params)
        _assert_search_parity(v1_response, v2_response, "School")

    await _retry_until_replicated(_check)


@pytest.mark.asyncio
async def test_v1_v2_head_school_returns_same_status(
    auth_header,
    retry_http_502,
    retry_until_synced,
    create_ou_using_python,
    random_ou_name,
):
    """V1 and V2 HEAD /schools/{name} return the same status code (200 or 404)."""
    school = await create_ou_using_python()
    nonexistent = random_ou_name()
    v1_url, v2_url = _make_base_urls()

    # Existing school: wait for Kelvin DB sync before asserting 200.
    v1_response = retry_http_502(requests.head, f"{v1_url}/schools/{school}", headers=auth_header)
    v2_response = await retry_until_synced(
        requests.head, f"{v2_url}/schools/{school}", headers=auth_header
    )
    assert v1_response.status_code == 200, f"v1 HEAD {school}: {v1_response.status_code}"
    assert v2_response.status_code == 200, f"v2 HEAD {school}: {v2_response.status_code}"

    # Nonexistent school: 404 is the expected final answer, do not retry on it.
    v1_response = retry_http_502(requests.head, f"{v1_url}/schools/{nonexistent}", headers=auth_header)
    v2_response = retry_http_502(requests.head, f"{v2_url}/schools/{nonexistent}", headers=auth_header)
    assert v1_response.status_code == 404, f"v1 HEAD {nonexistent}: {v1_response.status_code}"
    assert v2_response.status_code == 404, f"v2 HEAD {nonexistent}: {v2_response.status_code}"


# ── Roles ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("role_name", ALL_ROLE_NAMES)
async def test_v1_v2_get_role_returns_same_output(auth_header, retry_http_502, role_name):
    """V1 and V2 GET /roles/{name} return equivalent data for each built-in role."""
    v1_url, v2_url = _make_base_urls()

    def _check() -> None:
        v1_response = retry_http_502(requests.get, f"{v1_url}/roles/{role_name}", headers=auth_header)
        assert v1_response.status_code == 200, v1_response.reason
        v2_response = requests.get(f"{v2_url}/roles/{role_name}", headers=auth_header)
        assert v2_response.status_code == 200, v2_response.reason
        assert_responses_equal(v1_response.json(), v2_response.json())

    await _retry_until_replicated(_check)


@pytest.mark.asyncio
async def test_v1_v2_search_roles_returns_same_output(auth_header, retry_http_502):
    """V1 and V2 GET /roles/ return equivalent data for every role."""
    v1_url, v2_url = _make_base_urls()

    def _check() -> None:
        v1_response = retry_http_502(requests.get, f"{v1_url}/roles/", headers=auth_header)
        v2_response = requests.get(f"{v2_url}/roles/", headers=auth_header)
        _assert_search_parity(v1_response, v2_response, "Role")

    await _retry_until_replicated(_check)


# ── School Classes ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v1_v2_get_school_class_returns_same_output(
    auth_header,
    retry_http_502,
    create_ou_using_python,
    new_school_class_using_lib,
):
    """V1 and V2 GET /classes/{school}/{name} return equivalent data for the same class."""
    school = await create_ou_using_python()
    _dn, attrs = await new_school_class_using_lib(school)
    class_name = attrs["name"]
    v1_url, v2_url = _make_base_urls()

    def _check() -> None:
        v1_response = retry_http_502(
            requests.get, f"{v1_url}/classes/{school}/{class_name}", headers=auth_header
        )
        assert v1_response.status_code == 200, v1_response.reason
        v2_response = requests.get(f"{v2_url}/classes/{school}/{class_name}", headers=auth_header)
        assert v2_response.status_code == 200, v2_response.reason
        assert_responses_equal(v1_response.json(), v2_response.json())

    await _retry_until_replicated(_check)


@pytest.mark.asyncio
async def test_v1_v2_search_school_classes_returns_same_output(
    auth_header,
    retry_http_502,
    create_ou_using_python,
    new_school_class_using_lib,
):
    """V1 and V2 GET /classes/?school=… return equivalent data for every class."""
    school = await create_ou_using_python()
    await new_school_class_using_lib(school)
    await new_school_class_using_lib(school)
    v1_url, v2_url = _make_base_urls()

    params = {"school": school}

    def _check() -> None:
        v1_response = retry_http_502(
            requests.get, f"{v1_url}/classes/", headers=auth_header, params=params
        )
        v2_response = requests.get(f"{v2_url}/classes/", headers=auth_header, params=params)
        _assert_search_parity(v1_response, v2_response, "Class")

    await _retry_until_replicated(_check)


# ── Workgroups ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v1_v2_get_workgroup_returns_same_output(
    auth_header,
    retry_http_502,
    create_ou_using_python,
    new_workgroup_using_lib,
):
    """V1 and V2 GET /workgroups/{school}/{name} return equivalent data for the same workgroup."""
    school = await create_ou_using_python()
    _dn, attrs = await new_workgroup_using_lib(school)
    wg_name = attrs["name"]
    v1_url, v2_url = _make_base_urls()

    def _check() -> None:
        v1_response = retry_http_502(
            requests.get, f"{v1_url}/workgroups/{school}/{wg_name}", headers=auth_header
        )
        assert v1_response.status_code == 200, v1_response.reason
        v2_response = requests.get(f"{v2_url}/workgroups/{school}/{wg_name}", headers=auth_header)
        assert v2_response.status_code == 200, v2_response.reason
        assert_responses_equal(v1_response.json(), v2_response.json())

    await _retry_until_replicated(_check)


@pytest.mark.asyncio
async def test_v1_v2_search_workgroups_returns_same_output(
    auth_header,
    retry_http_502,
    create_ou_using_python,
    new_workgroup_using_lib,
):
    """V1 and V2 GET /workgroups/?school=… return equivalent data for every workgroup."""
    school = await create_ou_using_python()
    await new_workgroup_using_lib(school)
    await new_workgroup_using_lib(school)
    v1_url, v2_url = _make_base_urls()

    params = {"school": school}

    def _check() -> None:
        v1_response = retry_http_502(
            requests.get, f"{v1_url}/workgroups/", headers=auth_header, params=params
        )
        v2_response = requests.get(f"{v2_url}/workgroups/", headers=auth_header, params=params)
        _assert_search_parity(v1_response, v2_response, "Workgroup")

    await _retry_until_replicated(_check)
