import logging
from pathlib import Path

import pytest

from ucsschool.lib.models.user import User
from udm_rest_client import UDM
from univention.config_registry import ConfigRegistry

logging.basicConfig(level=logging.DEBUG, format="%(message)s", handlers=[logging.StreamHandler()])

ucr = ConfigRegistry()
ucr.load()


@pytest.mark.skipif(
    not Path("/var/lib/ucs-school-import/kelvin-hooks/add_school_admins_to_admin_group.py").exists(),
    reason="Custom hook not installed: add_school_admins_to_admin_group.py",
)
@pytest.mark.asyncio
async def test_add_school_admins_to_admin_group(
    ldap_base,
    create_ou_using_python,
    create_random_users,
    udm_kwargs,
    url_fragment,
    random_user_create_model,
    schedule_delete_user_name_using_udm,
    retry_http_502,
):
    """
    This test case tests the add_school_admins_to_admin_group hook.
    """
    # TODO: add third school where it is also school_admin
    school1 = await create_ou_using_python()  # school_admin
    school2 = await create_ou_using_python()  # school_admin

    user = (
        await create_random_users(
            ou_name=school1,
            roles={"school_admin": 1},
            schools=[
                f"{url_fragment}/schools/{school1}",
                f"{url_fragment}/schools/{school2}",
            ],
        )
    )[0]

    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school1, f"username={user.name}")
        udm_user = await udm.get("users/user").get(lib_users[0].dn)
        domadm_dn1 = (
            f"cn={ucr.get('ucsschool/ldap/default/groupprefix/admins', 'admins-')}"
            f"{school1.lower()},cn=ouadmins,cn=groups,{ldap_base}"
        )
        assert domadm_dn1 in udm_user.props.groups
        domadm_dn2 = (
            f"cn={ucr.get('ucsschool/ldap/default/groupprefix/admins', 'admins-')}"
            f"{school2.lower()},cn=ouadmins,cn=groups,{ldap_base}"
        )
        assert domadm_dn2 in udm_user.props.groups
