# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only


import logging
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Annotated, cast

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import Connection
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine
from ucsschool_objects import KelvinStorageSession

from ucsschool.kelvin.constants import ALEMBIC_CONFIG_FILE

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_alembic_head_revision() -> str:
    # Not CWD-relative: a relative path only resolves when the process
    # happens to start in /kelvin (gunicorn does, the test runner does not).
    # Override via the ALEMBIC_CONFIG env var, e.g. for uv-based dev runs.
    alembic_cfg = Config(toml_file=str(ALEMBIC_CONFIG_FILE))
    return ScriptDirectory.from_config(alembic_cfg).get_current_head()


async def get_db_engine(request: Request) -> AsyncEngine:
    return cast(AsyncEngine, request.app.state.db_engine)


async def get_health_check_db_engine(request: Request) -> AsyncEngine:
    return cast(AsyncEngine, request.app.state.health_check_db_engine)


def get_current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


async def check_db_compatibility(engine: AsyncEngine = Depends(get_db_engine)) -> None:
    head_revision = _get_alembic_head_revision()
    async with engine.connect() as connection:
        current_revision = await connection.run_sync(get_current_revision)
    if current_revision != head_revision:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This instance is deprecated. Please upgrade.",
        )


async def check_health_db_compatibility(
    engine: Annotated[AsyncEngine, Depends(get_health_check_db_engine)],
) -> None:
    """FastAPI dependency for /health only.

    Runs against a connection pool dedicated to /health (see
    build_app_lifespan), never shared with business traffic, so
    sqlalchemy.exc.TimeoutError here cannot be explained away as pool
    contention -- it means the database is genuinely unreachable, and
    /health must fail. /v2/* keeps using check_db_compatibility() directly,
    against the business-traffic engine, and stays strict.
    """
    try:
        await check_db_compatibility(engine)
    except SQLAlchemyTimeoutError as exc:
        logger.error(
            "check_health_db_compatibility: timed out waiting for the dedicated "
            "health-check connection; the database appears to be unreachable."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unreachable.",
        ) from exc


async def get_storage_session(request: Request) -> AsyncGenerator[KelvinStorageSession, None]:
    async with request.app.state.storage_session_factory.session_scope() as session:
        yield session
