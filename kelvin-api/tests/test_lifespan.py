# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import logging
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import make_url

from ucsschool.kelvin.service import lifespan as lifespan_module
from ucsschool.kelvin.service.lifespan import build_app_lifespan

HEAD_REVISION = "revision_123"


def _set_db_revision(db_path: Path, revision: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES (?)", (revision,))


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "kelvin.sqlite"


@pytest.fixture(autouse=True)
def _stub_non_db_startup_steps(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    monkeypatch.setattr(lifespan_module, "load_configs", lambda logger: None)
    monkeypatch.setattr(lifespan_module, "get_import_config", lambda: None)
    monkeypatch.setattr(lifespan_module, "log_version", lambda app, logger: None)
    monkeypatch.setattr(
        lifespan_module, "get_database_url", lambda: make_url(f"sqlite+aiosqlite:///{db_path}")
    )


@pytest.fixture
def app() -> FastAPI:
    return FastAPI(lifespan=build_app_lifespan(logging.getLogger(__name__)))


@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision", return_value=HEAD_REVISION)
def test_lifespan_starts_up_when_db_is_compatible(
    _mock_get_head: MagicMock, db_path: Path, app: FastAPI
) -> None:
    _set_db_revision(db_path, HEAD_REVISION)

    with TestClient(app):
        assert app.state.db_engine is not None


@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision", return_value=HEAD_REVISION)
def test_lifespan_fails_fast_when_db_is_not_migrated(
    _mock_get_head: MagicMock, db_path: Path, app: FastAPI
) -> None:
    # db_path is never populated, so the alembic_version table doesn't exist.
    with pytest.raises(RuntimeError, match="This instance is deprecated"):
        with TestClient(app):
            pass
