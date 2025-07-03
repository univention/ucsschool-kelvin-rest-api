# -*- coding: utf-8 -*-

# Copyright 2020-2022 Univention GmbH
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

import logging
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional

import uldap3
from asgi_correlation_id.context import correlation_id
from pydantic import BaseModel
from uldap3 import Entry, LdapConfig as uLdapConfig, escape_filter_chars

from ucsschool.lib.models.utils import env_or_ucr, uldap_admin_read_local

from .constants import API_USERS_GROUP_NAME, CN_ADMIN_PASSWORD_FILE, MACHINE_PASSWORD_FILE

logger = logging.getLogger(__name__)


@lru_cache
def get_uldap_conf(
    ldap_base: Optional[str] = None,
    host_dn: Optional[str] = None,
    host_fqdn: Optional[str] = None,
    host_port: Optional[int] = None,
    password_machine: Optional[str] = None,
    cn_admin_dn: str = "cn=admin",
    password_cn_admin: Optional[str] = None,
) -> uLdapConfig:
    if password_machine is None:
        with open(MACHINE_PASSWORD_FILE, "r") as f:
            password_machine = f.read().strip()
    if password_cn_admin is None:
        with open(CN_ADMIN_PASSWORD_FILE, "r") as f:
            password_cn_admin = f.read().strip()
    return uLdapConfig(
        ldap_base=ldap_base or env_or_ucr("ldap/base"),
        host_dn=host_dn or env_or_ucr("ldap/hostdn"),
        host_fqdn=host_fqdn or env_or_ucr("ldap/server/name"),
        host_port=host_port or int(env_or_ucr("ldap/server/port")),
        password_machine=password_machine,
        cn_admin_dn=cn_admin_dn,
        password_cn_admin=password_cn_admin,
    )


class LdapUser(BaseModel):
    username: str
    full_name: Optional[str] = None
    disabled: bool
    dn: str
    kelvin_admin: bool = False
    attributes: Optional[Dict[str, List[Any]]] = None


def admin_group_members() -> List[str]:
    ldap_base = env_or_ucr("ldap/base")
    search_filter = f"(cn={escape_filter_chars(API_USERS_GROUP_NAME)})"
    base = f"cn=groups,{ldap_base}"
    uldap = uldap_admin_read_local()
    results = uldap.search(search_filter=search_filter, attributes=["uniqueMember"], search_base=base)
    if len(results) == 1:
        return results[0]["uniqueMember"].values
    else:
        logger.error("Reading group %r from LDAP: results=%r", API_USERS_GROUP_NAME, results)
        return []


def user_is_disabled(ldap_result: Entry) -> bool:
    return (
        "D" in ldap_result["sambaAcctFlags"].value
        or ldap_result["krb5KDCFlags"].value == 254
        or (
            "shadowExpire" in ldap_result
            and ldap_result["shadowExpire"].value is not None
            and ldap_result["shadowExpire"].value < datetime.now().timestamp() / 3600 / 24
        )
    )


def get_user(
    username: str,
    bind_dn: Optional[str] = None,
    bind_pw: Optional[str] = None,
    attributes: List[str] = None,
    school_only=True,
) -> Optional[LdapUser]:
    """
    Get data of user `username`.

    :param str username: user to load
    :param str bind_dn: LDAP DN to bind with
    :param str bind_pw: password for `bind_dn`
    :param List[str] attributes: user LDAP attributes to read (optional)
    :param bool school_only: search only for school user objects (optional, default: True)
    :return: LdapUser object if user is found. None if not found or the LDAP bind was not successful.
    """
    if not attributes:
        attributes = [
            "displayName",
            "krb5KDCFlags",
            "sambaAcctFlags",
            "shadowExpire",
            "uid",
            "ucsschoolSchool",
            "ucsschoolRole",
        ]
    search_filter = f"(uid={escape_filter_chars(username)})"
    if school_only:
        search_filter = (
            f"(&{search_filter}(|"
            f"(objectClass=ucsschoolStaff)"
            f"(objectClass=ucsschoolStudent)"
            f"(objectClass=ucsschoolTeacher)"
            f"(objectClass=ucsschoolAdministrator)"
            f"))"
        )
    uldap = uldap_admin_read_local().user_account(user=bind_dn, password=bind_pw)
    results = uldap.search(
        search_filter,
        attributes=attributes,
    )
    if len(results) == 1:
        result = results[0]
        return LdapUser(
            username=result["uid"].value,
            full_name=result["displayName"].value,
            disabled=user_is_disabled(result),
            dn=result.entry_dn,
            attributes=result.entry_attributes_as_dict,
        )
    elif len(results) > 1:
        raise RuntimeError(
            f"More than 1 result when searching LDAP with filter {search_filter!r}: {results!r}."
        )
    else:
        return None


def get_dn_of_user(username: str) -> str:
    search_filter = f"(uid={escape_filter_chars(username)})"
    uldap = uldap_admin_read_local()
    results = uldap.search(search_filter=search_filter, attributes=None)
    if len(results) == 1:
        return results[0].entry_dn
    elif len(results) > 1:
        raise RuntimeError(
            f"More than 1 result when searching LDAP with filter {search_filter!r}: {results!r}."
        )
    else:
        return ""


def check_auth_and_get_user(username: str, password: str) -> Optional[LdapUser]:
    """
    Get user data if user exists and the password is correct.

    :param str username: user to load
    :param str password: password for `username`
    :return: LdapUser object if user is found and the password is correct, None otherwise.
    """
    user_dn = get_dn_of_user(username)
    if user_dn:
        try:
            user = get_user(username=username, bind_dn=user_dn, bind_pw=password, school_only=False)
        except uldap3.exceptions.BindError:
            user = None
        if user:
            admin_users = admin_group_members()
            if user_dn in admin_users:
                user.kelvin_admin = True
        else:
            logger.debug("Wrong password for existing user %r.", username)
        return user
    else:
        logger.debug("No such user in LDAP: %r.", username)
        return None


_udm_kwargs: Dict[str, str] = {}


def udm_kwargs() -> Dict[str, Any]:
    if not _udm_kwargs:
        uldap_config: uLdapConfig = get_uldap_conf()
        _udm_kwargs.update(
            {
                "username": uldap_config.cn_admin_dn.split(",", 1)[0],
                "password": uldap_config.password_cn_admin.get_secret_value(),
                "url": f"https://{uldap_config.host_fqdn}/univention/udm/",
            }
        )
    return {**_udm_kwargs, "request_id": correlation_id.get()}
