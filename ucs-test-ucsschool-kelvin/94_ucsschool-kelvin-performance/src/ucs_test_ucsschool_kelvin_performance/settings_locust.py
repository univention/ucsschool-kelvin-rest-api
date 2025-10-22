import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, overload

KELVIN_HOST_ENV = "UCS_ENV_KELVIN_HOST"
KELVIN_HOST_FALLBACK = "primary.ucsschool.test"
KELVIN_PASSWORD_ENV = "UCS_ENV_TEST_KELVIN_PASSWORD"  # nosec
KELVIN_PASSWORD_FALLBACK = "univention"  # nosec
KELVIN_USERNAME_ENV = "UCS_ENV_TEST_KELVIN_USERNAME"
KELVIN_USERNAME_FALLBACK = "Administrator"


@overload
def default_from_env(env: str, *, default: int) -> Callable[[], int]:
    ...


@overload
def default_from_env(env: str, *, default: str) -> Callable[[], str]:
    ...


@overload
def default_from_env(env: str, *, default: Path) -> Callable[[], Path]:
    ...


def default_from_env(env: str, *, default: int | str | Path) -> Callable[[], Path | int | str]:
    def _func() -> str | int | Path:
        if isinstance(default, Path):
            return Path(os.getenv(env, default))
        elif isinstance(default, str):
            return str(os.getenv(env, default))
        else:
            return int(os.getenv(env, default))

    return _func


@dataclass
class Settings:
    test_data_path: Path = field(
        default_factory=default_from_env("UCS_ENV_TEST_DATA_PATH", default=Path("/var/lib/test-data"))
    )
    kelvin_password: str = field(
        default_factory=default_from_env(KELVIN_PASSWORD_ENV, default=KELVIN_PASSWORD_FALLBACK)
    )
    kelvin_username: str = field(
        default_factory=default_from_env(KELVIN_USERNAME_ENV, default=KELVIN_USERNAME_FALLBACK)
    )
    token_renew_period: int = field(
        default_factory=default_from_env("UCS_ENV_TEST_TOKEN_RENEW_PERIOD", default=60)
    )
    kelvin_host: str = field(
        default_factory=default_from_env(KELVIN_HOST_ENV, default=KELVIN_HOST_FALLBACK)
    )
    roles: list[str] = field(
        default_factory=lambda: ["staff", "student", "teacher", "legal_guardian", "school_admin"]
    )


@lru_cache(maxsize=1)
def get_settings():
    return Settings()
