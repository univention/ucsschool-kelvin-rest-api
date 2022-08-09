import pytest


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
async def test_schoolname_validation(create_ou_using_python, udm_kwargs, ldap_base):
    """Test if an invalid school ou name is raising the expected exception

    - Related Bug: #54793
    """

    with pytest.raises(ValueError, match="'Invalid school name'"):
        _ou_name_kelvin = await create_ou_using_python(  # noqa: F841 for pytest output
            ou_name="ba€d_ou_name", cache=False
        )
