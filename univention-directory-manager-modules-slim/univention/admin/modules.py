# -*- coding: utf-8 -*-

# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import logging
import os
from collections import namedtuple
from typing import Any, List, Optional

from ldap.dn import explode_dn

from univention.config_registry import ConfigRegistry

from .client import UDM, HTTPError, Module, Object
from .filter import flatten_filter, parse as filter_parse
from .uexceptions import noObject

MACHINE_PASSWORD_FILE = "/etc/machine.secret"  # nosec
MachinePWCache = namedtuple("MachinePWCache", ["mtime", "password"])
logger = logging.getLogger(__name__)
_udm_http = None


class ConnectionData(object):
    """
    Connection details as it would be in a app Docker container.
    """

    _machine_pw = MachinePWCache(0, "")
    _ucr = None

    @classmethod
    def ucr(cls):
        if not cls._ucr:
            cls._ucr = ConfigRegistry()
            cls._ucr.load()
        return cls._ucr

    @classmethod
    def _env_or_ucr(cls, key):  # type: (str) -> str
        try:
            return os.environ[key.replace("/", "_")]
        except KeyError:
            return cls.ucr()[key]

    @classmethod
    def ldap_base(cls):  # type: () -> str
        return cls._env_or_ucr("ldap/base")

    @classmethod
    def ldap_hostdn(cls):  # type: () -> str
        return cls._env_or_ucr("ldap/hostdn")

    @classmethod
    def ldap_machine_account_username(cls):  # type: () -> str
        hostdn = cls.ldap_hostdn()
        if hostdn.startswith("cn=") or hostdn.startswith("uid="):
            return "{}$".format(explode_dn(hostdn, True)[0])
        else:
            return hostdn

    @classmethod
    def ldap_server_name(cls):  # type: () -> str
        return cls._env_or_ucr("ldap/server/name")

    @classmethod
    def machine_password(cls):  # type: () -> str
        """
        For developers: will try os.environ["ldap_machine_password"]
        before reading from /etc/machine.secret.
        """
        try:
            return os.environ["ldap_machine_password"]
        except KeyError:
            pass

        mtime = os.stat(MACHINE_PASSWORD_FILE).st_mtime
        if cls._machine_pw.mtime == mtime:
            return cls._machine_pw.password
        else:
            with open(MACHINE_PASSWORD_FILE, "r") as fp:
                pw = fp.read()
                pw = pw.strip()
            cls._machine_pw = MachinePWCache(mtime, pw)
            return pw

    @classmethod
    def uri(cls):  # type: () -> str
        # TODO: should be HTTPS
        return "http://{}/univention/udm/".format(cls.ldap_server_name())


def get_machine_connection():  # type: () -> UDM
    global _udm_http
    if not _udm_http:
        # print("uri={uri} username={username} password={password}".format(
        # 	uri=ConnectionData.uri(),
        # 	username=ConnectionData.ldap_machine_account_username(),
        # 	password=ConnectionData.machine_password())
        # )
        _udm_http = UDM.http(
            uri=ConnectionData.uri(),
            username=ConnectionData.ldap_machine_account_username(),
            password=ConnectionData.machine_password(),
        ).version(0)
    return _udm_http


def get(name):  # type: (str) -> Module
    """return UDM module"""
    return get_machine_connection().get(name)


def lookup(module_name, co, lo_udm, filter="", base="", superordinate=None, scope="sub"):
    # type: (str, Any, UDM, Optional[str], Optional[str], Optional[str], Optional[str]) -> List[Object]
    # logger.debug(
    # 	"*** module_name=%r co=%r lo_udm=%r filter=%r base=%r superordinate=%r scope=%r",
    # 	module_name, co, lo_udm, filter, base, superordinate, scope
    # )
    mod = lo_udm.get(module_name)  # type: Module
    filter_s_parsed = filter_parse(filter)
    if hasattr(filter_s_parsed, "expressions"):
        args = dict((e.variable, e.value) for e in flatten_filter(filter_s_parsed))
    else:
        args = (
            dict(((filter_s_parsed.variable, filter_s_parsed.value),))
            if filter_s_parsed.variable
            else {}
        )
    res = mod.search(filter=args, position=base, scope=scope, superordinate=superordinate, opened=True)
    try:
        return list(res)
    except HTTPError as exc:
        if exc.code in (404, 422):
            raise noObject(str(exc))


def init(lo, po, usersmod):
    # TODO
    pass


def update():
    pass
