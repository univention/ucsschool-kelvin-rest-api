# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only


from functools import lru_cache
from typing import AsyncGenerator, cast

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine
from ucsschool_objects import KelvinStorageSession

from ucsschool.kelvin.constants import ALEMBIC_CONFIG_FILE


@lru_cache(maxsize=1)
def _get_alembic_head_revision() -> str:
    # Not CWD-relative: a relative path only resolves when the process
    # happens to start in /kelvin (gunicorn does, the test runner does not).
    # Override via the ALEMBIC_CONFIG env var, e.g. for uv-based dev runs.
    alembic_cfg = Config(toml_file=str(ALEMBIC_CONFIG_FILE))
    return ScriptDirectory.from_config(alembic_cfg).get_current_head()


async def get_db_engine(request: Request) -> AsyncEngine:
    return cast(AsyncEngine, request.app.state.db_engine)


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


async def get_storage_session(request: Request) -> AsyncGenerator[KelvinStorageSession, None]:
    async with request.app.state.storage_session_factory.session_scope() as session:
        yield session
