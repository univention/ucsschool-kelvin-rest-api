import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable

from fastapi import FastAPI

from ..config import UDM_MAPPING_CONFIG, load_configurations
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
        yield

    return lifespan
