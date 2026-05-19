import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable

from fastapi import FastAPI
from ucsschool_objects.core.adapters.sqlalchemy import (
    DatabaseSettings,
    build_engine,
    build_kelvin_storage_session_factory,
)

from ..config import UDM_MAPPING_CONFIG, load_configurations
from ..database import get_database_url
from ..import_config import get_import_config
from .log import setup_logging


def load_configs(logger: logging.Logger) -> None:
    load_configurations()
    logger.info("UDM mapping configuration: %s", UDM_MAPPING_CONFIG)


def log_version(app: FastAPI, logger: logging.Logger) -> None:
    logger.info("Started %s version %s.", app.title, app.version)


def build_app_lifespan(logger: logging.Logger) -> Callable[[FastAPI], AsyncIterator[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        setup_logging()
        load_configs(logger)
        get_import_config()
        log_version(app, logger)
        settings = DatabaseSettings(url=get_database_url())
        engine = build_engine(settings)
        app.state.storage_session_factory = build_kelvin_storage_session_factory(engine)
        yield
        await engine.dispose()

    return lifespan
