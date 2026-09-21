# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import sqlite3
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from ucsschool.kelvin.main import app
from ucsschool.kelvin.service.dependency import (
    check_db_compatibility,
    get_db_engine,
    get_storage_session,
)

HEAD_REVISION = "revision_123"


async def _mock_storage_session() -> AsyncGenerator[MagicMock, None]:
    yield MagicMock()


def _set_db_revision(db_path: Path, revision: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES (?)", (revision,))


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "kelvin.sqlite"


@pytest.fixture
def engine(db_path: Path) -> AsyncEngine:
    return create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)


@pytest.fixture
def client(engine: AsyncEngine) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_storage_session] = _mock_storage_session
    app.dependency_overrides[get_db_engine] = lambda: engine
    yield TestClient(app)
    app.dependency_overrides.pop(get_storage_session, None)
    app.dependency_overrides.pop(get_db_engine, None)


@patch("ucsschool.kelvin.main.check_db_compatibility")
def test_v1_api_does_not_depend_on_db_compatibility(mock_check: MagicMock, client: TestClient) -> None:
    # Note: v1 does NOT have check_db_compatibility as a dependency.
    response = client.get("/ucsschool/kelvin/v1/roles/")
    # Status 401 means it proceeded past any non-existent DB check to authentication.
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    mock_check.assert_not_called()


async def test_get_db_engine_returns_the_engine_built_by_the_lifespan() -> None:
    request = MagicMock()
    request.app.state.db_engine = sentinel = object()

    assert await get_db_engine(request) is sentinel


@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision", return_value=HEAD_REVISION)
async def test_check_passes_when_the_revisions_match(
    _mock_get_head: MagicMock, db_path: Path, engine: AsyncEngine
) -> None:
    _set_db_revision(db_path, HEAD_REVISION)

    await check_db_compatibility(engine)


@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision", return_value=HEAD_REVISION)
async def test_check_raises_503_when_the_revisions_differ(
    _mock_get_head: MagicMock, db_path: Path, engine: AsyncEngine
) -> None:
    _set_db_revision(db_path, "revision_999")

    with pytest.raises(HTTPException) as excinfo:
        await check_db_compatibility(engine)

    assert excinfo.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert excinfo.value.detail == "This instance is deprecated. Please upgrade."


@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision", return_value=HEAD_REVISION)
async def test_check_raises_503_when_the_database_is_not_migrated(
    _mock_get_head: MagicMock, engine: AsyncEngine
) -> None:
    with pytest.raises(HTTPException) as excinfo:
        await check_db_compatibility(engine)

    assert excinfo.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision", return_value=HEAD_REVISION)
def test_v2_api_depends_on_db_compatibility_success(
    _mock_get_head: MagicMock, db_path: Path, client: TestClient
) -> None:
    _set_db_revision(db_path, HEAD_REVISION)

    response = client.get("/ucsschool/kelvin/v2/roles/")

    # Status 401 means the DB check dependency passed and it proceeded to authentication.
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision", return_value=HEAD_REVISION)
def test_v2_api_depends_on_db_compatibility_failure(
    _mock_get_head: MagicMock, db_path: Path, client: TestClient
) -> None:
    _set_db_revision(db_path, "revision_999")

    response = client.get("/ucsschool/kelvin/v2/roles/")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {"detail": "This instance is deprecated. Please upgrade."}
