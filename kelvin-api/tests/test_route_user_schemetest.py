# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import logging

import pytest
import requests

# reuse code from test_route_user.py
# ==> see below at test_patch-email_null_with_email_scheme
from test_route_user import compare_ldap_json_obj

import ucsschool.kelvin.constants
from ucsschool.importer.models.import_user import ImportUser
from ucsschool.kelvin.routers.user import UserModel
from ucsschool.lib.models.user import User
from ucsschool.lib.roles import role_student
from udm_rest_client import UDM

pytestmark = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.mark.asyncio
async def test_patch_email_null_with_email_scheme(
    auth_header,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    import_config_for_mail,
    reset_import_config_module,
    udm_kwargs,
):
    """
    Tries to PATCH an existing student user WITH existing scheme for "email" and sets the email to None.
    This test checks for a regression that happened in the Kelvin API 3.0.0.
    Since the Kelvin API is not able to accept the empty string "", the old behaviour had to be restored
    that accepted None to remove the email property.
    """
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, role_student, disabled=False)
    new_user_data = {"email": None}
    response = retry_http_502(
        requests.patch,
        f"{url_fragment}/users/{user.name}",
        headers=auth_header,
        json=new_user_data,
    )
    assert response.status_code == 200, f"{response.__dict__!r}"
    api_user = api_user = UserModel(**response.json())
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={user.name}")
        assert len(lib_users) == 1
        lib_user: User = lib_users[0]
        assert lib_user.email is None
    json_resp = response.json()
    compare_ldap_json_obj(api_user.dn, json_resp, url_fragment)


@pytest.mark.asyncio
async def test_patch_email_empty_string_with_email_scheme(
    auth_header,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    import_config_for_mail,
    reset_import_config_module,
    udm_kwargs,
):
    """
    Tries to PATCH an existing student user WITH existing scheme for "email" and sets the email to "".
    The UDM REST API will not accept this due to the syntax check for "email":
    the empty string does not contain a valid mail domain name.
    """
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, role_student, disabled=False)
    new_user_data = {"email": ""}
    response = retry_http_502(
        requests.patch,
        f"{url_fragment}/users/{user.name}",
        headers=auth_header,
        json=new_user_data,
    )
    assert response.status_code == 422, f"{response.__dict__!r}"
