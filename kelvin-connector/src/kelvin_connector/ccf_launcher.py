# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
"""Start the CCF binary with the Kelvin connector as its Python callback.

Derives the CCF configuration from the connector's existing one: the
subscription credentials from the App Center's provisioning config, the
CCF database from the Kelvin DB settings (in its own schema).
"""

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from loguru import logger
from sqlalchemy.engine import URL
from ucsschool_objects.core.adapters.sqlalchemy import build_settings

CCF_BINARY = "/usr/local/bin/ccf"
# Created by an alembic revision; also named there.
CCF_DB_SCHEMA = "ccf"
PROVISIONING_CONFIG_FILE = Path(
    "/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/provisioning/provisioning_config.json"
)
# Overridable through the environment.
CCF_DEFAULTS = {
    "MAX_ALLOWED_ERRORS": "3",
    "ASYNC_PROCESSING": "1",
    "PROVISIONING_ACCEPT_INVALID_CERTS": "false",
}


def ccf_database_url(kelvin_db_url: URL) -> str:
    return kelvin_db_url.set(
        drivername="postgres",
        query={"options": f"-csearch_path={CCF_DB_SCHEMA}"},
    ).render_as_string(hide_password=False)


def ccf_environment(
    environ: Mapping[str, str],
    provisioning_config: Mapping[str, object],
    database_url: str,
    python_path: list[str],
) -> dict[str, str]:
    env = {**CCF_DEFAULTS, **environ}
    env.update(
        PYTHON_CALLBACK="kelvin_connector.ccf_callback",
        # The CCF's embedded interpreter neither activates the venv nor reads
        # its .pth files (editable installs), so it gets this interpreter's path.
        PYTHON_CALLBACK_PATH=":".join(path for path in python_path if path),
        PROVISIONING_HOSTNAME=environ["PROVISIONING_FQDN"],
        PROVISIONING_NAME=str(provisioning_config["subscription_name"]),
        PROVISIONING_PASSWORD=str(provisioning_config["subscription_password"]),
        DATABASE_URL=database_url,
    )
    return env


def main() -> None:
    if not os.environ.get("PROVISIONING_FQDN"):
        logger.critical("Provisioning API FQDN is missing.")
        sys.exit(1)
    try:
        provisioning_config = cast("dict[str, object]", json.loads(PROVISIONING_CONFIG_FILE.read_text()))
        database_url = ccf_database_url(build_settings().url)
        env = ccf_environment(os.environ, provisioning_config, database_url, sys.path)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        logger.critical("Cannot configure the CCF: {!r}", exc)
        sys.exit(1)
    os.execve(CCF_BINARY, [CCF_BINARY], env)  # noqa: S606 -- fixed binary, no shell


if __name__ == "__main__":  # pragma: no cover
    main()
