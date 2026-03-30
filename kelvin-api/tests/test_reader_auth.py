# Copyright 2024 Univention GmbH
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
import requests
from fastapi import HTTPException

import ucsschool.kelvin.constants
from ucsschool.kelvin.ldap import LdapUser
from ucsschool.kelvin.token_auth import get_kelvin_admin, get_kelvin_reader

must_run_in_container = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)


def _make_user(kelvin_admin: bool = False, kelvin_reader: bool = False) -> LdapUser:
    """Helper: create a minimal LdapUser with given flags."""
    return LdapUser(
        username="testuser",
        disabled=False,
        dn="uid=testuser,cn=users,dc=example,dc=com",
        kelvin_admin=kelvin_admin,
        kelvin_reader=kelvin_reader,
    )


async def test_get_kelvin_reader_allows_reader_user():
    """A user with only kelvin_reader=True must pass get_kelvin_reader."""
    user = _make_user(kelvin_admin=False, kelvin_reader=True)
    result = get_kelvin_reader(user)
    assert result is user


async def test_get_kelvin_reader_allows_admin_user():
    """A kelvin_admin user must also pass get_kelvin_reader."""
    user = _make_user(kelvin_admin=True, kelvin_reader=False)
    result = get_kelvin_reader(user)
    assert result is user


async def test_get_kelvin_reader_allows_both_flags():
    """A user with both flags set must pass get_kelvin_reader."""
    user = _make_user(kelvin_admin=True, kelvin_reader=True)
    result = get_kelvin_reader(user)
    assert result is user


async def test_get_kelvin_admin_allows_both_flags():
    """A user with both flags set must pass get_kelvin_admin."""
    user = _make_user(kelvin_admin=True, kelvin_reader=True)
    result = get_kelvin_admin(user)
    assert result is user


async def test_get_kelvin_reader_rejects_unprivileged_user():
    """A user with neither flag must be denied with HTTP 401."""
    user = _make_user(kelvin_admin=False, kelvin_reader=False)
    with pytest.raises(HTTPException) as exc_info:
        get_kelvin_reader(user)
    assert exc_info.value.status_code == 401


async def test_get_kelvin_admin_allows_admin_user():
    """A kelvin_admin user must pass get_kelvin_admin."""
    user = _make_user(kelvin_admin=True, kelvin_reader=False)
    result = get_kelvin_admin(user)
    assert result is user


async def test_get_kelvin_admin_rejects_reader_only_user():
    """A reader-only user must be denied by get_kelvin_admin with HTTP 401."""
    user = _make_user(kelvin_admin=False, kelvin_reader=True)
    with pytest.raises(HTTPException) as exc_info:
        get_kelvin_admin(user)
    assert exc_info.value.status_code == 401


async def test_get_kelvin_admin_rejects_unprivileged_user():
    """A user with neither flag must be denied by get_kelvin_admin with HTTP 401."""
    user = _make_user(kelvin_admin=False, kelvin_reader=False)
    with pytest.raises(HTTPException) as exc_info:
        get_kelvin_admin(user)
    assert exc_info.value.status_code == 401


@must_run_in_container
@pytest.mark.parametrize(
    "endpoint,params,expected_status_code",
    [
        pytest.param(*x, id=x[0])
        for x in [
            ("/roles/", {}, 200),
            ("/roles/student", {}, 200),
            ("/schools/", {}, 200),
            ("/classes/", {"school": "DEMOSCHOOL"}, 200),
            ("/classes/DEMOSCHOOL/democlass", {}, 200),
            ("/workgroups/", {"school": "DEMOSCHOOL"}, 200),
            ("/workgroups/DEMOSCHOOL/demowg", {}, 404),
            ("/users/", {}, 200),
        ]
    ],
)
async def test_reader_token_accepted_on_get_endpoint(
    retry_http_502, url_fragment, generate_auth_header, endpoint, params, expected_status_code
):
    """A reader JWT must receive 200 on a GET endpoint."""
    auth_header = await generate_auth_header(username="Administrator", is_admin=False, is_reader=True)
    response = retry_http_502(
        requests.get, f"{url_fragment}{endpoint}", headers=auth_header, params=params
    )
    assert (
        response.status_code == expected_status_code
    ), f"Reader should be allowed on GET {endpoint}. Got {response.status_code}: {response.text}"


@must_run_in_container
@pytest.mark.parametrize(
    "endpoint",
    ["/schools/DEMOSCHOOL"],
)
async def test_reader_token_accepted_on_head_endpoint(
    retry_http_502, url_fragment, generate_auth_header, endpoint
):
    """A reader JWT must receive 200 on a HEAD endpoint."""
    auth_header = await generate_auth_header(username="Administrator", is_admin=False, is_reader=True)
    response = retry_http_502(requests.head, f"{url_fragment}{endpoint}", headers=auth_header)
    assert (
        response.status_code == 200
    ), f"Reader should be allowed on HEAD {endpoint}. Got {response.status_code}: {response.text}"


@must_run_in_container
@pytest.mark.parametrize(
    "endpoint",
    [
        "/schools/",
        "/classes/",
        "/workgroups/",
        "/users/",
    ],
)
async def test_reader_token_rejected_on_post_endpoint(
    retry_http_502, url_fragment, generate_auth_header, endpoint
):
    """A reader JWT must receive 401 on a POST endpoint."""
    auth_header = await generate_auth_header(username="Administrator", is_admin=False, is_reader=True)
    response = retry_http_502(requests.post, f"{url_fragment}{endpoint}", headers=auth_header)
    assert (
        response.status_code == 401
    ), f"Reader should be rejected on POST {endpoint}. Got {response.status_code}: {response.text}"


@must_run_in_container
@pytest.mark.parametrize(
    "endpoint",
    [
        "/classes/a/b",
        "/workgroups/a/b",
        "/users/a",
    ],
)
async def test_reader_token_rejected_on_delete_endpoint(
    retry_http_502, url_fragment, generate_auth_header, endpoint
):
    """A reader JWT must receive 401 when attempting a DELETE endpoint."""
    auth_header = await generate_auth_header(username="Administrator", is_admin=False, is_reader=True)
    response = retry_http_502(
        requests.delete,
        f"{url_fragment}{endpoint}",
        headers=auth_header,
    )
    assert (
        response.status_code == 401
    ), f"Reader should be forbidden on DELETE {endpoint}. Got {response.status_code}: {response.text}"


@must_run_in_container
@pytest.mark.parametrize(
    "endpoint",
    ["/classes/a/b", "/workgroups/a/b", "/users/a"],
)
async def test_reader_token_rejected_on_patch_endpoint(
    retry_http_502, url_fragment, generate_auth_header, endpoint
):
    """A reader JWT must receive 401 when attempting a PATCH endpoint."""
    auth_header = await generate_auth_header(username="Administrator", is_admin=False, is_reader=True)
    response = retry_http_502(
        requests.patch,
        f"{url_fragment}{endpoint}",
        headers=auth_header,
    )
    assert (
        response.status_code == 401
    ), f"Reader should be forbidden on PATCH {endpoint}. Got {response.status_code}: {response.text}"


@must_run_in_container
@pytest.mark.parametrize(
    "endpoint",
    ["/classes/a/b", "/workgroups/a/b", "/users/a"],
)
async def test_reader_token_rejected_on_put_endpoint(
    retry_http_502, url_fragment, generate_auth_header, endpoint
):
    """A reader JWT must receive 401 when attempting a PUT endpoint."""
    auth_header = await generate_auth_header(username="Administrator", is_admin=False, is_reader=True)
    response = retry_http_502(
        requests.put,
        f"{url_fragment}{endpoint}",
        headers=auth_header,
    )
    assert (
        response.status_code == 401
    ), f"Reader should be forbidden on PUT {endpoint}. Got {response.status_code}: {response.text}"
