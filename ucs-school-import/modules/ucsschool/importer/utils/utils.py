# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
Diverse helper functions.
"""

from contextlib import contextmanager

import univention.admin.modules


def get_ldap_mapping_for_udm_property(udm_prop, udm_type):
    """
    Get the name of the LDAP attribute, a UDM property is mapped to.

    :param str udm_prop: name of UDM property
    :param str udm_type: name of UDM module (e.g. 'users/user')
    :returns: name of LDAP attribute or empty str if no mapping was found
    :rtype: str
    """
    return univention.admin.modules.get(udm_type).mapping.mapName(udm_prop)


@contextmanager
def nullcontext():
    """Context manager that does nothing."""
    yield None
