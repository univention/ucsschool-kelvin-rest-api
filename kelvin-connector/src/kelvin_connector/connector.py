import asyncio
import os
import sys
from pathlib import Path

from kelvin_connector.nubus_compat import sqlalchemy_mapper_factory
from kelvin_connector.sync import SynchronizationManager
from loguru import logger
from provisioning_consumer_lib import ConsumerModule
from ucsschool_objects.core.adapters.sqlalchemy.session import (
    build_engine,
    build_kelvin_storage_session_factory,
    build_settings,
)

from .consumer import KelvinConnectorEventHandler


def main():
    LDAP_SERVER_TYPE = os.environ.get("LDAP_SERVER_TYPE", None)
    if LDAP_SERVER_TYPE is None or LDAP_SERVER_TYPE != "master":
        logger.critical(f"Connector cannot run on {LDAP_SERVER_TYPE=}.")
        sys.exit(1)

    PROVISIONING_API_FQDN = os.environ.get("PROVISIONING_FQDN", None)
    if PROVISIONING_API_FQDN is None:
        logger.critical("Provisioning API FQDN is missing.")
        sys.exit(1)

    try:
        settings = build_settings()
    except RuntimeError as e:
        logger.critical(str(e))
        sys.exit(1)

    engine = build_engine(settings)
    storage_factory = build_kelvin_storage_session_factory(engine)
    synchronization_manager = SynchronizationManager(
        storage_factory=storage_factory,
        mapper_factory=sqlalchemy_mapper_factory,
    )

    CONFIG_DIR = Path("/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/")

    event_handler = KelvinConnectorEventHandler(synchronization_manager, logger=logger)
    consumer = ConsumerModule(
        event_handler,
        name="kelvin-connector",
        provisioning_url=f"https://{PROVISIONING_API_FQDN}/univention/provisioning",
        config_dir=CONFIG_DIR,
    )

    asyncio.run(consumer.consume_loop())
