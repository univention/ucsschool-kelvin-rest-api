# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only


from functools import lru_cache
from typing import AsyncGenerator

from fastapi import HTTPException, Request, status
from sqlalchemy import create_engine
from ucsschool_objects import KelvinStorageSession

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from ucsschool.kelvin.constants import ALEMBIC_CONFIG_FILE
from ucsschool.kelvin.database import get_database_url


@lru_cache(maxsize=1)
def _get_alembic_head_revision() -> str:
    # Not CWD-relative: a relative path only resolves when the process
    # happens to start in /kelvin (gunicorn does, the test runner does not).
    # Override via the ALEMBIC_CONFIG env var, e.g. for uv-based dev runs.
    alembic_cfg = Config(toml_file=str(ALEMBIC_CONFIG_FILE))
    return ScriptDirectory.from_config(alembic_cfg).get_current_head()


def check_db_compatibility() -> bool:
    head_revision = _get_alembic_head_revision()
    database_url = get_database_url()
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_revision = context.get_current_revision()
            connection.commit()
    finally:
        engine.dispose()
    if current_revision != head_revision:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This instance is deprecated. Please upgrade.",
        )


async def get_storage_session(request: Request) -> AsyncGenerator[KelvinStorageSession, None]:
    async with request.app.state.storage_session_factory.session_scope() as session:
        yield session
