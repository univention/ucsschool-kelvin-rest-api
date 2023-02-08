import logging
from pathlib import Path

import pytest

from ucsschool.lib.models.user import User
from ucsschool.lib.schoolldap import SchoolSearchBase
from udm_rest_client import UDM

logging.basicConfig(format="%(message)s", handlers=[logging.StreamHandler()])


@pytest.mark.skipif(
    not Path("/var/lib/ucs-school-import/kelvin-hooks/add_school_admins_to_admin_group.py").exists(),
    reason="Custom hook not installed: add_school_admins_to_admin_group.py",
)
@pytest.mark.asyncio
async def test_add_school_admins_to_admin_group(
    create_ou_using_python,
    create_random_users,
    udm_kwargs,
    url_fragment,
):
    """
    This test case tests the add_school_admins_to_admin_group hook.
    """
    school1 = await create_ou_using_python()
    school2 = await create_ou_using_python()

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
        domadm_dn1: str = SchoolSearchBase([school1]).admins_group
        assert domadm_dn1 in udm_user.props.groups
        domadm_dn2: str = SchoolSearchBase([school2]).admins_group
        assert domadm_dn2 in udm_user.props.groups
