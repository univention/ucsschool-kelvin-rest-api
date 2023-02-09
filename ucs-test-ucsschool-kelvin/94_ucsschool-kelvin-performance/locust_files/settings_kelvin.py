import contextlib
import os

KELVIN_HOST_ENV = "UCS_ENV_KELVIN_HOST"
KELVIN_HOST_FALLBACK = "primary.school.test"
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
