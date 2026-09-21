# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import logging
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import AsyncIterator, Callable

from fastapi import FastAPI, HTTPException
from ucsschool_objects.core.adapters.sqlalchemy import (
    DatabaseSettings,
    build_engine,
    build_kelvin_storage_session_factory,
)

from ..config import UDM_MAPPING_CONFIG, load_configurations
from ..database import get_database_url
from ..import_config import get_import_config
from .dependency import check_db_compatibility
from .log import setup_logging


def load_configs(logger: logging.Logger) -> None:
    load_configurations()
    logger.info("UDM mapping configuration: %s", UDM_MAPPING_CONFIG)


def log_version(app: FastAPI, logger: logging.Logger) -> None:
    logger.info("Started %s version %s.", app.title, app.version)


def build_app_lifespan(logger: logging.Logger) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        setup_logging()
        load_configs(logger)
        get_import_config()
        log_version(app, logger)
        settings = DatabaseSettings(url=get_database_url())
        engine = build_engine(settings)
        app.state.db_engine = engine
        app.state.storage_session_factory = build_kelvin_storage_session_factory(engine)

        # A separate engine/pool dedicated to /health: business traffic never
        # checks out a connection from it, so a timeout on it can only mean
        # the database itself is unreachable, never business-traffic pool
        # contention (see check_health_db_compatibility).
        health_check_engine = build_engine(
            DatabaseSettings(url=get_database_url(), pool_size=1, max_overflow=0)
        )
        app.state.health_check_db_engine = health_check_engine

        try:
            await check_db_compatibility(engine)
        except HTTPException as exc:
            raise RuntimeError(str(exc.detail)) from exc
        yield
        await engine.dispose()
        await health_check_engine.dispose()

    return lifespan
