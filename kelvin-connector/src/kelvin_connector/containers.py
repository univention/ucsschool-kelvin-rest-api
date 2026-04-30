from __future__ import annotations

from dependency_injector import containers, providers
from loguru import logger
from provisioning_consumer_lib import ConsumerModule
from ucsschool_objects.core.adapters.sqlalchemy.session import (
    build_engine,
    build_kelvin_storage_session_factory,
    build_settings,
)

from .event_handler import KelvinConnectorEventHandler
from .sync import SynchronizationManager


class ConnectorContainer(containers.DeclarativeContainer):
    """Dependency-injector container for connector composition wiring."""

    config = providers.Configuration()

    settings = providers.Singleton(build_settings)
    engine = providers.Singleton(build_engine, settings=settings)
    storage_factory = providers.Singleton(build_kelvin_storage_session_factory, engine=engine)

    synchronization_manager = providers.Factory(
        SynchronizationManager,
        storage_factory=storage_factory,
    )

    event_handler = providers.Factory(
        KelvinConnectorEventHandler,
        synchronization_manager=synchronization_manager,
        logger=logger,
    )

    provisioning_url = providers.Callable(
        lambda fqdn: f"https://{fqdn}/univention/provisioning",
        config.provisioning_fqdn,
    )

    consumer_module = providers.Factory(
        ConsumerModule,
        event_handler,
        name="kelvin-connector",
        provisioning_url=provisioning_url,
        config_dir=config.config_dir,
    )
