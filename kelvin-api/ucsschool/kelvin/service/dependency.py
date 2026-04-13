# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from functools import lru_cache

from fastapi import HTTPException, status
from sqlalchemy import create_engine

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from ucsschool.kelvin.database import get_database_url


@lru_cache(maxsize=1)
def _get_alembic_head_revision() -> str:
    alembic_cfg = Config(toml_file="./pyproject.toml")
    return ScriptDirectory.from_config(alembic_cfg).get_current_head()


def check_db_compatibility() -> bool:
    head_revision = _get_alembic_head_revision()
    database_url = get_database_url()
    engine = create_engine(database_url)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        current_revision = context.get_current_revision()
    if current_revision != head_revision:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This instance is deprecated. Please upgrade.",
        )
