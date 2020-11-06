# -*- coding: utf-8 -*-

# Copyright 2020 Univention GmbH
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
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from async_property import async_cached_property
from ldap3 import (
    AUTO_BIND_TLS_BEFORE_BIND,
    MODIFY_REPLACE,
    SIMPLE,
    Connection,
    Entry,
    Server,
)
from ldap3.core.exceptions import LDAPBindError, LDAPExceptionError
from ldap3.utils.conv import escape_filter_chars
from pydantic import BaseModel

from ucsschool.lib.models.utils import env_or_ucr

from .constants import (
    API_USERS_GROUP_NAME,
    CN_ADMIN_PASSWORD_FILE,
    MACHINE_PASSWORD_FILE,
    UCS_SSL_CA_CERT,
)

_udm_kwargs: Dict[str, str] = {}


async def udm_kwargs():
    if not _udm_kwargs:
        ldap_access = LDAPAccess()
        _udm_kwargs.update(
            {
                "username": ldap_access.cn_admin,
                "password": await ldap_access.cn_admin_password,
                "url": f"https://{ldap_access.host}/univention/udm/",
                "ssl_ca_cert": UCS_SSL_CA_CERT,
            }
        )
    return _udm_kwargs


class LdapUser(BaseModel):
    username: str
    full_name: str = None
    disabled: bool
    dn: str
    attributes: Dict[str, List[Any]] = None


class LDAPAccess:
    ldap_base: str
    host: str
    host_dn: str
    port: int

    def __init__(self, ldap_base=None, host=None, host_dn=None, port=None):
        self.logger = logging.getLogger(__name__)
        self.ldap_base = ldap_base or env_or_ucr("ldap/base")
        self.host = host or env_or_ucr("ldap/master")
        self.host_dn = host_dn or env_or_ucr("ldap/hostdn")
        self.port = port or int(env_or_ucr("ldap/server/port"))
        self.cn_admin = "cn=admin"
        self.server = Server(host=self.host, port=self.port, get_info="ALL")

    @async_cached_property
    async def cn_admin_password(self):
        return await self._load_password(CN_ADMIN_PASSWORD_FILE)

    @async_cached_property
    async def machine_password(self):
        return await self._load_password(MACHINE_PASSWORD_FILE)

    @classmethod
    async def _load_password(cls, path: Path) -> str:
        async with aiofiles.open(path, "r") as fp:
            pw = await fp.read()
        return pw.strip()

    async def check_auth_and_get_user(
        self, username: str, password: str
    ) -> Optional[LdapUser]:
        user_dn = await self.get_dn_of_user(username)
        if user_dn:
            admin_group_members = await self.admin_group_members()
            if user_dn in admin_group_members:
                return await self.get_user(
                    username, user_dn, password, school_only=False
                )
            else:
                self.logger.debug(
                    "User %r not member of group %r.", username, API_USERS_GROUP_NAME
                )
                return None
        else:
            self.logger.debug("No such user in LDAP: %r.", username)
            return None

    async def search(
        self,
        filter_s: str,
        attributes: List[str] = None,
        base: str = None,
        bind_dn: str = None,
        bind_pw: str = None,
        raise_on_bind_error: bool = True,
    ) -> List[Entry]:
        base = base or self.ldap_base
        bind_dn = bind_dn or self.host_dn
        bind_pw = bind_pw or await self.machine_password
        try:
            with Connection(
                self.server,
                user=bind_dn,
                password=bind_pw,
                auto_bind=AUTO_BIND_TLS_BEFORE_BIND,
                authentication=SIMPLE,
                read_only=True,
            ) as conn:
                conn.search(base, filter_s, attributes=attributes)
        except LDAPExceptionError as exc:
            if isinstance(exc, LDAPBindError) and not raise_on_bind_error:
                return []
            self.logger.exception(
                "When connecting to %r with bind_dn %r: %s",
                self.server.host,
                bind_dn,
                exc,
            )
            raise
        return conn.entries

    async def modify(
        self,
        dn: str,
        changes: Dict[str, List[Any]],
        bind_dn: str = None,
        bind_pw: str = None,
        raise_on_bind_error: bool = True,
    ) -> bool:
        """
        Modify attributes, *replaces* value(s).

        `changes` should be: {'sn': ['foo'], 'uid': ['bar']}

        (Change usage of MODIFY_REPLACE to change behavior.)
        """
        bind_dn = bind_dn or f"{self.cn_admin},{self.ldap_base}"
        bind_pw = bind_pw or await self.cn_admin_password
        change_arg = dict((k, [(MODIFY_REPLACE, v)]) for k, v in changes.items())
        try:
            with Connection(
                self.server,
                user=bind_dn,
                password=bind_pw,
                auto_bind=AUTO_BIND_TLS_BEFORE_BIND,
                authentication=SIMPLE,
                read_only=False,
            ) as conn:
                return conn.modify(dn, change_arg)
        except LDAPExceptionError as exc:
            if isinstance(exc, LDAPBindError) and not raise_on_bind_error:
                return False
            self.logger.exception(
                "When connecting to %r with bind_dn %r: %s",
                self.server.host,
                bind_dn,
                exc,
            )
            raise

    async def get_dn_of_user(self, username: str) -> str:
        filter_s = f"(uid={escape_filter_chars(username)})"
        results = await self.search(filter_s, attributes=None)
        if len(results) == 1:
            return results[0].entry_dn
        elif len(results) > 1:
            raise RuntimeError(
                f"More than 1 result when searching LDAP with filter {filter_s!r}: {results!r}."
            )
        else:
            return ""

    @staticmethod
    def user_is_disabled(ldap_result: Entry) -> bool:
        return (
            "D" in ldap_result["sambaAcctFlags"].value
            or ldap_result["krb5KDCFlags"].value == 254
            or (
                "shadowExpire" in ldap_result
                and ldap_result["shadowExpire"].value is not None
                and ldap_result["shadowExpire"].value
                < datetime.now().timestamp() / 3600 / 24
            )
        )

    async def get_user(
        self,
        username: str,
        bind_dn: str = None,
        bind_pw: str = None,
        attributes: List[str] = None,
        school_only=True,
    ) -> Optional[LdapUser]:
        if not attributes:
            attributes = [
                "displayName",
                "krb5KDCFlags",
                "sambaAcctFlags",
                "shadowExpire",
                "uid",
            ]
        filter_s = f"(uid={escape_filter_chars(username)})"
        if school_only:
            filter_s = (
                f"(&{filter_s}(|"
                f"(objectClass=ucsschoolStaff)"
                f"(objectClass=ucsschoolStudent)"
                f"(objectClass=ucsschoolTeacher)"
                f"))"
            )
        results = await self.search(
            filter_s,
            attributes,
            bind_dn=bind_dn,
            bind_pw=bind_pw,
            raise_on_bind_error=False,
        )
        if len(results) == 1:
            result = results[0]
            return LdapUser(
                username=result["uid"].value,
                full_name=result["displayName"].value,
                disabled=self.user_is_disabled(result),
                dn=result.entry_dn,
                attributes=result.entry_attributes_as_dict,
            )
        elif len(results) > 1:
            raise RuntimeError(
                f"More than 1 result when searching LDAP with filter {filter_s!r}: {results!r}."
            )
        else:
            return None

    async def admin_group_members(self) -> List[str]:
        filter_s = f"(cn={escape_filter_chars(API_USERS_GROUP_NAME)})"
        base = f"cn=groups,{self.ldap_base}"
        results = await self.search(filter_s, ["uniqueMember"], base=base)
        if len(results) == 1:
            return results[0]["uniqueMember"].values
        else:
            self.logger.error(
                "Reading group %r from LDAP: results=%r", API_USERS_GROUP_NAME, results
            )
            return []
