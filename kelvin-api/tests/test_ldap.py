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

from collections.abc import Sequence
from unittest.mock import Mock, patch

import ldap3
import pytest
from ldap3.core.exceptions import LDAPMaximumRetriesError, LDAPSocketOpenError
from ldap3.strategy.sync import SyncStrategy

import ucsschool.kelvin.constants
import ucsschool.kelvin.ldap
import ucsschool.lib.models.utils
from udm_rest_client import UDM

must_run_in_container = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)


def test_immediate_reconnect_strategy_is_installed():
    ucsschool.kelvin.ldap._install_immediate_reconnect_strategy()
    connection = ldap3.Connection(
        ldap3.Server("ldap.example.com", port=7389),
        client_strategy=ldap3.RESTARTABLE,
        lazy=True,
    )
    assert isinstance(
        connection.strategy, ucsschool.kelvin.ldap.FirstAttemptImmediateRestartableStrategy
    )


def test_first_reconnect_attempt_is_immediate_then_backs_off():
    """First retry must not sleep; subsequent retries use the configured sleep time."""
    connection = Mock(closed=True, usage=None, server_pool=None)
    strategy = ucsschool.kelvin.ldap.FirstAttemptImmediateRestartableStrategy(connection)
    strategy.restartable_sleep_time = 2  # configured between-retries backoff
    strategy.restartable_tries = 3  # finite, so the loop terminates

    sleeps = []
    with patch.object(
        SyncStrategy, "_open_socket", side_effect=LDAPSocketOpenError("server down")
    ), patch("ldap3.strategy.restartable.sleep", side_effect=lambda seconds: sleeps.append(seconds)):
        with pytest.raises(LDAPMaximumRetriesError):
            strategy._open_socket(("ldap.example.com", 7389))

    # 1st attempt immediate (0s), the remaining attempts wait the configured 2s.
    assert sleeps == [0, 2, 2]


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
