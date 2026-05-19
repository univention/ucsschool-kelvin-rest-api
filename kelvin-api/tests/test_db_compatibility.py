# Copyright 2026 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU AGPL V3.

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from ucsschool.kelvin.main import app
from ucsschool.kelvin.service.dependency import check_db_compatibility, get_storage_session


async def _mock_storage_session():
    yield MagicMock()


@pytest.fixture
def client():
    app.dependency_overrides[get_storage_session] = _mock_storage_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_storage_session, None)


@patch("ucsschool.kelvin.main.check_db_compatibility")
def test_v1_api_does_not_depend_on_db_compatibility(mock_check, client):
    # Note: v1 does NOT have check_db_compatibility as a dependency.
    response = client.get("/ucsschool/kelvin/v1/roles/")
    # Status 401 means it proceeded past any non-existent DB check to authentication.
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    mock_check.assert_not_called()


@patch("ucsschool.kelvin.database.env_or_ucr")
@patch("ucsschool.kelvin.database.Path.read_text")
@patch("ucsschool.kelvin.service.dependency.create_engine")
@patch("ucsschool.kelvin.service.dependency.MigrationContext.configure")
@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision")
def test_v2_api_depends_on_db_compatibility_success(
    mock_get_head,
    mock_migration_context,
    mock_create_engine,
    mock_read_text,
    mock_env_or_ucr,
    client,
):
    # Setup mocks
    mock_get_head.return_value = "revision_123"

    def env_or_ucr_mock(key):
        if key == "ucsschool/kelvin/db/uri":
            return "postgresql://localhost/kelvin"
        return f"dummy_{key}"

    mock_env_or_ucr.side_effect = env_or_ucr_mock
    mock_read_text.return_value = "dummy_password"

    mock_context = MagicMock()
    mock_context.get_current_revision.return_value = "revision_123"
    mock_migration_context.return_value = mock_context

    mock_engine = MagicMock()
    mock_create_engine.return_value = mock_engine

    # Execute (should not raise exception)
    check_db_compatibility()
    response = client.get("/ucsschool/kelvin/v2/roles/")
    # Status 401 means the DB check dependency passed and it proceeded to authentication.
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@patch("ucsschool.kelvin.database.env_or_ucr")
@patch("ucsschool.kelvin.database.Path.read_text")
@patch("ucsschool.kelvin.service.dependency.create_engine")
@patch("ucsschool.kelvin.service.dependency.MigrationContext.configure")
@patch("ucsschool.kelvin.service.dependency._get_alembic_head_revision")
def test_v2_api_depends_on_db_compatibility_failure(
    mock_get_head,
    mock_migration_context,
    mock_create_engine,
    mock_read_text,
    mock_env_or_ucr,
    client,
):
    # Setup mocks
    mock_get_head.return_value = "revision_123"

    def env_or_ucr_mock(key):
        if key == "ucsschool/kelvin/db/uri":
            return "postgresql://localhost/kelvin"
        return f"dummy_{key}"

    mock_env_or_ucr.side_effect = env_or_ucr_mock
    mock_read_text.return_value = "dummy_password"

    mock_context = MagicMock()
    mock_context.get_current_revision.return_value = "revision_999"  # Mismatch!
    mock_migration_context.return_value = mock_context

    mock_engine = MagicMock()
    mock_create_engine.return_value = mock_engine

    # Execute & Assert
    with pytest.raises(HTTPException) as excinfo:
        check_db_compatibility()

    assert excinfo.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert excinfo.value.detail == "This instance is deprecated. Please upgrade."
    response = client.get("/ucsschool/kelvin/v2/roles/")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {"detail": "This instance is deprecated. Please upgrade."}
