from functools import lru_cache
from pathlib import Path

from pydantic import BaseSettings, Field

from .settings_kelvin import (
    KELVIN_HOST_ENV,
    KELVIN_PASSWORD_ENV,
    KELVIN_USERNAME_ENV,
    kelvin_host as _kelvin_host,
    kelvin_password as _kelvin_password,
    kelvin_username as _kelvin_username,
)


class Settings(BaseSettings):
    test_data_path: Path = Field(env="UCS_ENV_TEST_DATA_PATH", default="/var/lib/test-data")
    kelvin_password: str = Field(env=KELVIN_PASSWORD_ENV, default=_kelvin_password())
    kelvin_username: str = Field(env=KELVIN_USERNAME_ENV, default=_kelvin_username())
    token_renew_period: int = Field(env="UCS_ENV_TEST_TOKEN_RENEW_PERIOD", default=60)
    kelvin_host: str = Field(env=KELVIN_HOST_ENV, default=_kelvin_host())
    roles = ["staff", "student", "teacher"]

    class Config:
        allow_population_by_field_name = True
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings():
    return Settings()
