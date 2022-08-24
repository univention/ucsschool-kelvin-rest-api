import pytest

import ucsschool.lib.create_ou as _create_ou
from ucsschool.lib.models.utils import ucr
from udm_rest_client import UDM


def _inside_docker():
    try:
        import ucsschool.kelvin.constants
    except ImportError:
        return False
    return ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists()


pytestmark = pytest.mark.skipif(
    not _inside_docker(),
    reason="Must run inside Docker container started by appcenter.",
)


@pytest.mark.asyncio
async def test_schoolname_validation(create_ou_using_python):
    """Test if an invalid school ou name is raising the expected exception

    - Related Bug: #54793
    """

    with pytest.raises(ValueError, match="'Invalid school name'"):
        await create_ou_using_python(ou_name="ba€d_ou_name", cache=False)


@pytest.mark.asyncio
async def test_create_ou_validation(mocker, docker_host_name, ldap_base, udm_kwargs):
    mocker.patch("ucsschool.lib.models.school.School.create", return_value=True)
    underscore_ou_name = "underscore_ou_name"
    is_single_master = ucr.is_true("ucsschool/singlemaster", False)
    async with UDM(**udm_kwargs) as udm:
        with pytest.raises(ValueError, match=r"'Invalid Domain Controller name'"):
            await _create_ou.create_ou(
                ou_name=underscore_ou_name,
                display_name=underscore_ou_name,
                edu_name="not_allowed",
                admin_name="not_allowed",
                share_name="not_allowed",
                lo=udm,
                baseDN=ldap_base,
                hostname=docker_host_name,
                is_single_master=is_single_master,
            )
        try:
            await _create_ou.create_ou(
                ou_name=underscore_ou_name,
                display_name=underscore_ou_name,
                edu_name="edu-name123",
                admin_name="admin-name123",
                share_name="share-name123",
                lo=udm,
                baseDN=ldap_base,
                hostname=docker_host_name,
                is_single_master=is_single_master,
            )
        except ValueError:
            assert False, "Ou name %r is allowed but validation failed " % underscore_ou_name
