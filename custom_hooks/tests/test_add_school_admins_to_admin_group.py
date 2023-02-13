import logging

import pytest

from univention.config_registry import ConfigRegistry
from univention.udm import UDM

logging.basicConfig(level=logging.DEBUG, format="%(message)s", handlers=[logging.StreamHandler()])

ucr = ConfigRegistry()
ucr.load()


@pytest.mark.asyncio
async def test_add_school_admins_to_admin_group(get_base, kelvin_create_user_with_role):
    """
    This test case tests the add_school_admins_to_admin_group hook.
    """

    # Kelvin REST-API call to create the user with role
    resp = await kelvin_create_user_with_role(role="school_admin:school:DEMOSCHOOL")
    assert resp.status_code == 201

    user_name = resp.json()["name"]

    # Init udm object
    usermod = UDM.admin().version(2).get("users/user")
    domadm_dn = (
        f"cn={ucr.get('ucsschool/ldap/default/groupprefix/admins', 'admins-')}"
        f"demoschool,cn=ouadmins,cn=groups,{ucr['ldap/base']}"
    )

    for obj in usermod.search("uid=%s" % user_name):
        assert domadm_dn in obj.props.groups
