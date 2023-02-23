import contextlib
import os

KELVIN_HOST_ENV = "UCS_ENV_KELVIN_HOST"
KELVIN_HOST_FALLBACK = "primary.school.test"
KELVIN_PASSWORD_ENV = "UCS_ENV_TEST_KELVIN_PASSWORD"  # nosec
KELVIN_PASSWORD_FALLBACK = "univention"  # nosec
KELVIN_USERNAME_ENV = "UCS_ENV_TEST_KELVIN_USERNAME"
KELVIN_USERNAME_FALLBACK = "Administrator"
KELVIN_URL_BASE = "/ucsschool/kelvin/v1"


def kelvin_host() -> str:
    with contextlib.suppress(KeyError):
        host = os.environ[KELVIN_HOST_ENV]
        print(f"Using Kelvin host from environment variable {KELVIN_HOST_ENV!r}: {host!r}")
        return host
    with contextlib.suppress(ImportError):
        import univention.testing.ucr

        ucr = univention.testing.ucr.UCSTestConfigRegistry()
        ucr.load()
        host = ucr["ldap/master"]
        print(f"Using primary domain controller as Kelvin host (from UCR): {host!r}")
        return host
    print(f"Using hard coded fallback as Kelvin host: {KELVIN_HOST_FALLBACK!r}")
    return KELVIN_HOST_FALLBACK


def kelvin_password() -> str:
    with contextlib.suppress(KeyError):
        pw = os.environ[KELVIN_PASSWORD_ENV]
        print(f"Using Kelvin password from environment variable {KELVIN_PASSWORD_ENV!r}: {pw!r}")
        return pw
    print(f"Using hard coded fallback as Kelvin password: {KELVIN_PASSWORD_FALLBACK!r}")
    return KELVIN_PASSWORD_FALLBACK


def kelvin_username() -> str:
    with contextlib.suppress(KeyError):
        username = os.environ[KELVIN_USERNAME_ENV]
        print(f"Using Kelvin username from environment variable {KELVIN_USERNAME_ENV!r}: {username!r}")
        return username
    print(f"Using hard coded fallback as Kelvin username: {KELVIN_USERNAME_FALLBACK!r}")
    return KELVIN_USERNAME_FALLBACK
