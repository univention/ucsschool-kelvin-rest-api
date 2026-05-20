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

import os
import random
from typing import Any, NamedTuple, Type, Union

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


# ── Users ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v1_v2_get_user_returns_same_output(
    auth_header,
    retry_http_502,
    retry_until_synced,
    create_ou_using_python,
    new_import_user,
    import_config,
):
    """V1 and V2 GET /users/{username} return equivalent data for the same user."""
    role: _Role = random.choice(USER_ROLES)
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, role.name)

    v1_url, v2_url = _make_base_urls()

    v1_response = retry_http_502(requests.get, f"{v1_url}/users/{user.name}", headers=auth_header)
    assert v1_response.status_code == 200, v1_response.reason

    v2_response = await retry_until_synced(
        requests.get, f"{v2_url}/users/{user.name}", headers=auth_header
    )
    assert v2_response.status_code == 200, v2_response.reason

    assert_responses_equal(v1_response.json(), v2_response.json())


@pytest.mark.asyncio
async def test_v1_v2_search_users_returns_same_output(
    auth_header,
    retry_http_502,
    retry_until_synced,
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

    v1_response = retry_http_502(
        requests.get, f"{v1_url}/users/", headers=auth_header, params={"school": school}
    )
    assert v1_response.status_code == 200, v1_response.reason

    v2_response = await retry_until_synced(
        requests.get, f"{v2_url}/users/", headers=auth_header, params={"school": school}
    )
    assert v2_response.status_code == 200, v2_response.reason

    v1_users = {u["name"]: u for u in v1_response.json()}
    v2_users = {u["name"]: u for u in v2_response.json()}

    assert set(v1_users) == set(v2_users), (
        f"User sets differ: only in v1={set(v1_users) - set(v2_users)}, "
        f"only in v2={set(v2_users) - set(v1_users)}"
    )
    for name in v1_users:
        assert_responses_equal(v1_users[name], v2_users[name])


# ── Schools ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v1_v2_get_school_returns_same_output(
    auth_header,
    retry_http_502,
    retry_until_synced,
    create_ou_using_python,
):
    """V1 and V2 GET /schools/{name} return equivalent data for the same school."""
    school = await create_ou_using_python()
    v1_url, v2_url = _make_base_urls()

    v1_response = retry_http_502(requests.get, f"{v1_url}/schools/{school}", headers=auth_header)
    assert v1_response.status_code == 200, v1_response.reason

    v2_response = await retry_until_synced(
        requests.get, f"{v2_url}/schools/{school}", headers=auth_header
    )
    assert v2_response.status_code == 200, v2_response.reason

    assert_responses_equal(v1_response.json(), v2_response.json())


@pytest.mark.asyncio
async def test_v1_v2_search_schools_returns_same_output(
    auth_header,
    retry_http_502,
    retry_until_synced,
    create_ou_using_python,
    random_ou_name,
):
    """V1 and V2 GET /schools/?name=… return equivalent data for every matching school."""
    common_name = random_ou_name()
    await create_ou_using_python(ou_name=f"{common_name}a")
    await create_ou_using_python(ou_name=f"{common_name}b")
    v1_url, v2_url = _make_base_urls()

    params = {"name": f"{common_name}*"}
    v1_response = retry_http_502(requests.get, f"{v1_url}/schools/", headers=auth_header, params=params)
    assert v1_response.status_code == 200, v1_response.reason

    v2_response = await retry_until_synced(
        requests.get, f"{v2_url}/schools/", headers=auth_header, params=params
    )
    assert v2_response.status_code == 200, v2_response.reason

    v1_schools = {s["name"]: s for s in v1_response.json()}
    v2_schools = {s["name"]: s for s in v2_response.json()}

    assert set(v1_schools) == set(v2_schools), (
        f"School sets differ: only in v1={set(v1_schools) - set(v2_schools)}, "
        f"only in v2={set(v2_schools) - set(v1_schools)}"
    )
    for name in v1_schools:
        assert_responses_equal(v1_schools[name], v2_schools[name])


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
async def test_v1_v2_get_role_returns_same_output(
    auth_header, retry_http_502, retry_until_synced, role_name
):
    """V1 and V2 GET /roles/{name} return equivalent data for each built-in role."""
    v1_url, v2_url = _make_base_urls()

    v1_response = retry_http_502(requests.get, f"{v1_url}/roles/{role_name}", headers=auth_header)
    assert v1_response.status_code == 200, v1_response.reason

    v2_response = await retry_until_synced(
        requests.get, f"{v2_url}/roles/{role_name}", headers=auth_header
    )
    assert v2_response.status_code == 200, v2_response.reason

    assert_responses_equal(v1_response.json(), v2_response.json())


@pytest.mark.asyncio
async def test_v1_v2_search_roles_returns_same_output(auth_header, retry_http_502, retry_until_synced):
    """V1 and V2 GET /roles/ return equivalent data for every role."""
    v1_url, v2_url = _make_base_urls()

    v1_response = retry_http_502(requests.get, f"{v1_url}/roles/", headers=auth_header)
    assert v1_response.status_code == 200, v1_response.reason

    v2_response = await retry_until_synced(requests.get, f"{v2_url}/roles/", headers=auth_header)
    assert v2_response.status_code == 200, v2_response.reason

    v1_roles = {r["name"]: r for r in v1_response.json()}
    v2_roles = {r["name"]: r for r in v2_response.json()}

    assert set(v1_roles) == set(v2_roles), (
        f"Role sets differ: only in v1={set(v1_roles) - set(v2_roles)}, "
        f"only in v2={set(v2_roles) - set(v1_roles)}"
    )
    for name in v1_roles:
        assert_responses_equal(v1_roles[name], v2_roles[name])


# ── School Classes ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v1_v2_get_school_class_returns_same_output(
    auth_header,
    retry_http_502,
    retry_until_synced,
    create_ou_using_python,
    new_school_class_using_lib,
):
    """V1 and V2 GET /classes/{school}/{name} return equivalent data for the same class."""
    school = await create_ou_using_python()
    _dn, attrs = await new_school_class_using_lib(school)
    class_name = attrs["name"]
    v1_url, v2_url = _make_base_urls()

    v1_response = retry_http_502(
        requests.get, f"{v1_url}/classes/{school}/{class_name}", headers=auth_header
    )
    assert v1_response.status_code == 200, v1_response.reason

    v2_response = await retry_until_synced(
        requests.get, f"{v2_url}/classes/{school}/{class_name}", headers=auth_header
    )
    assert v2_response.status_code == 200, v2_response.reason

    assert_responses_equal(v1_response.json(), v2_response.json())


@pytest.mark.asyncio
async def test_v1_v2_search_school_classes_returns_same_output(
    auth_header,
    retry_http_502,
    retry_until_synced,
    create_ou_using_python,
    new_school_class_using_lib,
):
    """V1 and V2 GET /classes/?school=… return equivalent data for every class."""
    school = await create_ou_using_python()
    await new_school_class_using_lib(school)
    await new_school_class_using_lib(school)
    v1_url, v2_url = _make_base_urls()

    params = {"school": school}
    v1_response = retry_http_502(requests.get, f"{v1_url}/classes/", headers=auth_header, params=params)
    assert v1_response.status_code == 200, v1_response.reason

    v2_response = await retry_until_synced(
        requests.get, f"{v2_url}/classes/", headers=auth_header, params=params
    )
    assert v2_response.status_code == 200, v2_response.reason

    v1_classes = {c["name"]: c for c in v1_response.json()}
    v2_classes = {c["name"]: c for c in v2_response.json()}

    assert set(v1_classes) == set(v2_classes), (
        f"Class sets differ: only in v1={set(v1_classes) - set(v2_classes)}, "
        f"only in v2={set(v2_classes) - set(v1_classes)}"
    )
    for name in v1_classes:
        assert_responses_equal(v1_classes[name], v2_classes[name])


# ── Workgroups ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v1_v2_get_workgroup_returns_same_output(
    auth_header,
    retry_http_502,
    retry_until_synced,
    create_ou_using_python,
    new_workgroup_using_lib,
):
    """V1 and V2 GET /workgroups/{school}/{name} return equivalent data for the same workgroup."""
    school = await create_ou_using_python()
    _dn, attrs = await new_workgroup_using_lib(school)
    wg_name = attrs["name"]
    v1_url, v2_url = _make_base_urls()

    v1_response = retry_http_502(
        requests.get, f"{v1_url}/workgroups/{school}/{wg_name}", headers=auth_header
    )
    assert v1_response.status_code == 200, v1_response.reason

    v2_response = await retry_until_synced(
        requests.get, f"{v2_url}/workgroups/{school}/{wg_name}", headers=auth_header
    )
    assert v2_response.status_code == 200, v2_response.reason

    assert_responses_equal(v1_response.json(), v2_response.json())


@pytest.mark.asyncio
async def test_v1_v2_search_workgroups_returns_same_output(
    auth_header,
    retry_http_502,
    retry_until_synced,
    create_ou_using_python,
    new_workgroup_using_lib,
):
    """V1 and V2 GET /workgroups/?school=… return equivalent data for every workgroup."""
    school = await create_ou_using_python()
    await new_workgroup_using_lib(school)
    await new_workgroup_using_lib(school)
    v1_url, v2_url = _make_base_urls()

    params = {"school": school}
    v1_response = retry_http_502(
        requests.get, f"{v1_url}/workgroups/", headers=auth_header, params=params
    )
    assert v1_response.status_code == 200, v1_response.reason

    v2_response = await retry_until_synced(
        requests.get, f"{v2_url}/workgroups/", headers=auth_header, params=params
    )
    assert v2_response.status_code == 200, v2_response.reason

    v1_workgroups = {w["name"]: w for w in v1_response.json()}
    v2_workgroups = {w["name"]: w for w in v2_response.json()}

    assert set(v1_workgroups) == set(v2_workgroups), (
        f"Workgroup sets differ: only in v1={set(v1_workgroups) - set(v2_workgroups)}, "
        f"only in v2={set(v2_workgroups) - set(v1_workgroups)}"
    )
    for name in v1_workgroups:
        assert_responses_equal(v1_workgroups[name], v2_workgroups[name])
