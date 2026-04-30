# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import os
import sys
from pathlib import Path

from kelvin_connector.containers import ConnectorContainer
from loguru import logger


def main():
    LDAP_SERVER_TYPE = os.environ.get("LDAP_SERVER_TYPE", None)
    if LDAP_SERVER_TYPE is None or LDAP_SERVER_TYPE != "master":
        logger.critical(f"Connector cannot run on {LDAP_SERVER_TYPE=}.")
        sys.exit(1)

    PROVISIONING_API_FQDN = os.environ.get("PROVISIONING_FQDN", None)
    if PROVISIONING_API_FQDN is None:
        logger.critical("Provisioning API FQDN is missing.")
        sys.exit(1)

    CONFIG_DIR = Path("/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/")
    container = ConnectorContainer()
    container.config.provisioning_fqdn.from_value(PROVISIONING_API_FQDN)
    container.config.config_dir.from_value(CONFIG_DIR)

    try:
        consumer = container.consumer_module()
    except RuntimeError as e:
        logger.critical(str(e))
        sys.exit(1)

    consumer.consume_loop()
