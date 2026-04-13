# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from collections.abc import Sequence
from unittest.mock import patch

import pytest

import ucsschool.kelvin.constants
import ucsschool.kelvin.ldap
import ucsschool.lib.models.utils
from udm_rest_client import UDM

must_run_in_container = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)


def test_get_uldap_conf_props(temp_file_func, random_name):
    tmp_file1 = temp_file_func()
    txt1 = random_name()
    tmp_file1.write_text(txt1)
    tmp_file2 = temp_file_func()
    txt2 = random_name()
    tmp_file2.write_text(txt2)
    with patch.object(ucsschool.kelvin.ldap, "CN_ADMIN_PASSWORD_FILE", tmp_file1), patch(
        "ucsschool.kelvin.ldap.MACHINE_PASSWORD_FILE", tmp_file2
    ), patch("ucsschool.kelvin.ldap._udm_kwargs", {}):
        ucsschool.kelvin.ldap.get_uldap_conf.cache_clear()
        uldap = ucsschool.kelvin.ldap.get_uldap_conf()
        assert uldap.cn_admin_dn == f"cn=admin,{uldap.ldap_base}"
        assert txt1 == uldap.password_cn_admin.get_secret_value()
        assert txt2 == uldap.password_machine.get_secret_value()


def test_udm_kwargs_fake(temp_file_func, random_name):
    tmp_file1 = temp_file_func()
    txt1 = random_name()
    tmp_file1.write_text(txt1)
    tmp_file2 = temp_file_func()
    with patch("ucsschool.kelvin.ldap.CN_ADMIN_PASSWORD_FILE", tmp_file1), patch(
        "ucsschool.kelvin.ldap.MACHINE_PASSWORD_FILE", tmp_file2
    ), patch("ucsschool.kelvin.ldap._udm_kwargs", {}):
        ucsschool.kelvin.ldap.get_uldap_conf.cache_clear()
        udm_kwargs = ucsschool.kelvin.ldap.udm_kwargs()
    assert udm_kwargs["username"] == "cn=admin"
    assert udm_kwargs["password"] == txt1
    host = ucsschool.lib.models.utils.env_or_ucr("ldap/server/name")
    assert udm_kwargs["url"] == f"https://{host}/univention/udm/"


@must_run_in_container
def test_get_user():
    username = "Administrator"
    ucsschool.kelvin.ldap.get_uldap_conf.cache_clear()
    uldap = ucsschool.kelvin.ldap.get_uldap_conf()
    user_obj = ucsschool.kelvin.ldap.get_user(username, school_only=False)
    assert isinstance(user_obj, ucsschool.kelvin.ldap.LdapUser)
    assert user_obj.dn == f"uid={username},cn=users,{uldap.ldap_base}"


@must_run_in_container
def test_admin_group_members():
    username = "Administrator"
    ucsschool.kelvin.ldap.get_uldap_conf.cache_clear()
    uldap = ucsschool.kelvin.ldap.get_uldap_conf()
    members = ucsschool.kelvin.ldap.admin_group_members()
    administrator_dn = f"uid={username},cn=users,{uldap.ldap_base}"
    assert isinstance(members, Sequence)
    assert administrator_dn in members


@must_run_in_container
@pytest.mark.asyncio
async def test_udm_kwargs_real():
    ucsschool.kelvin.ldap.get_uldap_conf.cache_clear()
    uldap = ucsschool.kelvin.ldap.get_uldap_conf()
    udm_kwargs = ucsschool.kelvin.ldap.udm_kwargs()
    async with UDM(**udm_kwargs) as udm:
        base_dn = await udm.session.base_dn
        assert base_dn == uldap.ldap_base
