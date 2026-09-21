# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import sqlite3
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from ucsschool.kelvin.main import app
from ucsschool.kelvin.service.dependency import (
    check_db_compatibility,
    check_health_db_compatibility,
    get_db_engine,
    get_health_check_db_engine,
    get_storage_session,
)

HEAD_REVISION = "revision_123"


def _raise_pool_timeout(*_args: object, **_kwargs: object) -> None:
    raise SQLAlchemyTimeoutError("QueuePool limit reached, connection timed out")


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
    app.dependency_overrides[get_health_check_db_engine] = lambda: engine
    yield TestClient(app)
    app.dependency_overrides.pop(get_storage_session, None)
    app.dependency_overrides.pop(get_db_engine, None)
    app.dependency_overrides.pop(get_health_check_db_engine, None)


@pytest.fixture
def pool_timeout_engine() -> MagicMock:
    """Mock engine whose connect() raises immediately.

    Simulates SQLAlchemy's own pool checkout timeout firing
    (sqlalchemy.exc.TimeoutError).
    """
    engine = MagicMock()
    engine.connect = _raise_pool_timeout
    return engine


@pytest.fixture
def pool_timeout_client(pool_timeout_engine: MagicMock) -> Generator[TestClient, None, None]:
    """TestClient wired to pool_timeout_engine via the get_db_engine override.

    Drives HTTP requests through routes while the pool's checkout timeout
    fires immediately.
    """
    app.dependency_overrides[get_storage_session] = _mock_storage_session
    app.dependency_overrides[get_db_engine] = lambda: pool_timeout_engine
    yield TestClient(app)
    app.dependency_overrides.pop(get_storage_session, None)
    app.dependency_overrides.pop(get_db_engine, None)


@pytest.fixture
def pool_timeout_health_client(pool_timeout_engine: MagicMock) -> Generator[TestClient, None, None]:
    """TestClient wired to pool_timeout_engine via the get_health_check_db_engine override.

    Drives HTTP requests through /health while its dedicated connection's checkout
    timeout fires immediately.
    """
    app.dependency_overrides[get_storage_session] = _mock_storage_session
    app.dependency_overrides[get_health_check_db_engine] = lambda: pool_timeout_engine
    yield TestClient(app)
    app.dependency_overrides.pop(get_storage_session, None)
    app.dependency_overrides.pop(get_health_check_db_engine, None)


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


@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision", return_value=HEAD_REVISION)
async def test_check_db_compatibility_propagates_pooled_connection_timeout_uncaught(
    _mock_get_head: MagicMock,
    pool_timeout_engine: MagicMock,
) -> None:
    """Strict path (/v2/*, startup): with pool_timeout_engine, a pool timeout is not swallowed."""
    with pytest.raises(SQLAlchemyTimeoutError):
        await check_db_compatibility(pool_timeout_engine)


@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision", return_value=HEAD_REVISION)
async def test_check_health_db_compatibility_raises_503_when_sqlalchemy_pool_timeout_fires(
    _mock_get_head: MagicMock,
    caplog: pytest.LogCaptureFixture,
    pool_timeout_engine: MagicMock,
) -> None:
    """The dedicated health-check engine's own pool checkout timeout is a real DB-unreachable

    signal (nothing else ever contends for it), so it must fail /health, not be swallowed.
    """
    with caplog.at_level("ERROR"):
        with pytest.raises(HTTPException) as excinfo:
            await check_health_db_compatibility(pool_timeout_engine)

    assert excinfo.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "timed out" in caplog.text


@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision", return_value=HEAD_REVISION)
def test_health_endpoint_ok_when_db_compatible(
    _mock_get_head: MagicMock, db_path: Path, client: TestClient
) -> None:
    """Baseline via client/engine (real SQLite): /health returns 200 when the DB schema matches head."""
    _set_db_revision(db_path, HEAD_REVISION)

    response = client.get("/health")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision", return_value=HEAD_REVISION)
def test_health_endpoint_fails_when_the_dedicated_health_connection_times_out(
    _mock_get_head: MagicMock,
    pool_timeout_health_client: TestClient,
) -> None:
    """/health uses its own dedicated engine (see build_app_lifespan), never shared with

    business traffic, so a timeout on it is never business-traffic pool contention -- it
    means the database is unreachable, and /health must fail.
    """
    response = pool_timeout_health_client.get("/health")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {"detail": "Database is unreachable."}


@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision", return_value=HEAD_REVISION)
def test_v2_api_still_fails_when_pooled_connection_times_out(
    _mock_get_head: MagicMock,
    pool_timeout_client: TestClient,
) -> None:
    """Business traffic stays strict: via pool_timeout_client, contention must not relax /v2/*."""
    with pytest.raises(SQLAlchemyTimeoutError):
        pool_timeout_client.get("/ucsschool/kelvin/v2/roles/")
