#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
"""
Univention Common Python Library
"""

# SPDX-FileCopyrightText: 2012 - 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from typing import Optional

import univention.config_registry


def getLDAPURIs(configRegistryInstance=None):
    # type: (Optional[univention.config_registry.ConfigRegistry]) -> str
    """
    Returns a space separated list of all configured |LDAP| servers, according to |UCR| variables
    `ldap/server/name` and `ldap/server/addition`.

    :param univention.config_registry.ConfigRegistry configRegistryInstance: An optional |UCR| instance.
    :returns: A space separated list of |LDAP| |URI|.
    :rtype: str
    """
    if configRegistryInstance:
        ucr = configRegistryInstance
    else:
        ucr = univention.config_registry.ConfigRegistry()
        ucr.load()

    uri_string = ""
    ldaphosts = []
    port = ucr.get("ldap/server/port", "7389")
    ldap_server_name = ucr.get("ldap/server/name")
    ldap_server_addition = ucr.get("ldap/server/addition")

    if ldap_server_name:
        ldaphosts.append(ldap_server_name)
    if ldap_server_addition:
        ldaphosts.extend(ldap_server_addition.split())
    if ldaphosts:
        urilist = ["ldap://%s:%s" % (host, port) for host in ldaphosts]
        uri_string = " ".join(urilist)

    return uri_string


def getLDAPServersCommaList(configRegistryInstance=None):
    # type: (Optional[univention.config_registry.ConfigRegistry]) -> str
    """
    Returns a comma-separated string with all configured |LDAP| servers,
    `ldap/server/name` and `ldap/server/addition`.

    :param univention.config_registry.ConfigRegistry configRegistryInstance: An optional |UCR| instance.
    :returns: A space separated list of |LDAP| host names.
    :rtype: str
    """
    if configRegistryInstance:
        ucr = configRegistryInstance
    else:
        ucr = univention.config_registry.ConfigRegistry()
        ucr.load()

    ldap_servers = ""
    ldaphosts = []
    ldap_server_name = ucr.get("ldap/server/name")
    ldap_server_addition = ucr.get("ldap/server/addition")

    if ldap_server_name:
        ldaphosts.append(ldap_server_name)
    if ldap_server_addition:
        ldaphosts.extend(ldap_server_addition.split())
    if ldaphosts:
        ldap_servers = ",".join(ldaphosts)

    return ldap_servers


def custom_username(name, configRegistryInstance=None):
    # type: (str, Optional[univention.config_registry.ConfigRegistry]) -> str
    """
    Returns the customized user name configured via |UCR|.

    :param str name: A user name.
    :param univention.config_registry.ConfigRegistry configRegistryInstance: An optional |UCR| instance.
    :returns: The translated user name.
    :rtype: str
    :raises ValueError: if no name is given.
    """
    if not name:
        raise ValueError()

    if configRegistryInstance:
        ucr = configRegistryInstance
    else:
        ucr = univention.config_registry.ConfigRegistry()
        ucr.load()

    return ucr.get("users/default/" + name.lower().replace(" ", ""), name)


def custom_groupname(name, configRegistryInstance=None):
    # type: (str, Optional[univention.config_registry.ConfigRegistry]) -> str
    """
    Returns the customized group name configured via |UCR|.

    :param str name: A group name.
    :param univention.config_registry.ConfigRegistry configRegistryInstance: An optional |UCR| instance.
    :returns: The translated group name.
    :rtype: str
    :raises ValueError: if no name is given.
    """
    if not name:
        raise ValueError()

    if configRegistryInstance:
        ucr = configRegistryInstance
    else:
        ucr = univention.config_registry.ConfigRegistry()
        ucr.load()

    return ucr.get("groups/default/" + name.lower().replace(" ", "")) or name
