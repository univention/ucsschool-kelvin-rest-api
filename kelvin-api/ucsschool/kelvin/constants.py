# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import logging
from pathlib import Path

import lazy_object_proxy

from ucsschool.kelvin import get_version


def _app_version() -> str:
    return get_version()


APP_ID = "ucsschool-kelvin-rest-api"
APP_VERSION = lazy_object_proxy.Proxy(_app_version)
API_USERS_GROUP_NAME = f"{APP_ID}-admins"
APP_BASE_PATH = Path("/var/lib/univention-appcenter/apps", APP_ID)
APP_CONFIG_BASE_PATH = APP_BASE_PATH / "conf"
KELVIN_CONFIG_BASE_PATH = Path("/etc/ucsschool/kelvin")
CN_ADMIN_PASSWORD_FILE = APP_CONFIG_BASE_PATH / "cn_admin.secret"
DEFAULT_LOG_LEVELS = {
    None: logging.INFO,
    "fastapi": logging.INFO,
    "multipart": logging.WARNING,
    "requests": logging.INFO,
    "udm_rest_client": logging.INFO,
    "univention": logging.INFO,
    "ucsschool": logging.INFO,
    "uvicorn.access": logging.INFO,
    "uvicorn.error": logging.INFO,
    "alembic": logging.WARNING,
    "sqlalchemy": logging.WARNING,
}
IMPORT_CONFIG_FILE_DEFAULT = Path("/usr/share/ucs-school-import/configs/kelvin_defaults.json")
IMPORT_CONFIG_FILE_USER = Path("/var/lib/ucs-school-import/configs/kelvin.json")
KELVIN_IMPORTUSER_HOOKS_PATH = Path("/var/lib/ucs-school-import/kelvin-hooks")
MACHINE_PASSWORD_FILE = "/etc/machine.secret"  # nosec
STATIC_FILES_PATH = Path("/kelvin/kelvin-api/static")
STATIC_FILE_CHANGELOG = STATIC_FILES_PATH / "changelog.html"
STATIC_FILE_README = STATIC_FILES_PATH / "readme.html"
TOKEN_SIGN_SECRET_FILE = APP_CONFIG_BASE_PATH / "tokens.secret"
TOKEN_HASH_ALGORITHM = "HS256"  # nosec
UDM_MAPPED_PROPERTIES_CONFIG_FILE = KELVIN_CONFIG_BASE_PATH / "mapped_udm_properties.json"
UCRV_TOKEN_TTL = "ucsschool/kelvin/access_tokel_ttl"  # nosec
URL_KELVIN_BASE = "/ucsschool/kelvin"
URL_API_V1_PREFIX = f"{URL_KELVIN_BASE}/v1"
URL_API_V2_PREFIX = f"{URL_KELVIN_BASE}/v2"
URL_TOKEN_BASE = f"{URL_KELVIN_BASE}/token"
