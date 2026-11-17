# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from kelvin_connector.connector import (
    DEFAULT_KELVIN_HEALTH_URL,
    DEFAULT_TASK_TIMEOUT,
    ConnectorSetupError,
    build_runner,
)
from kelvin_connector.tasks import TaskRunner


@pytest.fixture
def good_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LDAP_SERVER_TYPE", "master")
    monkeypatch.delenv("KELVIN_CONNECTOR_TASK_TIMEOUT", raising=False)
    monkeypatch.delenv("KELVIN_HEALTH_URL", raising=False)


@pytest.fixture
def urlopen() -> Iterator[MagicMock]:
    with patch("kelvin_connector.connector.urllib.request.urlopen") as p_urlopen:
        yield p_urlopen


@pytest.fixture
def mocked_setup(urlopen: MagicMock) -> Iterator[MagicMock]:
    with (
        patch("kelvin_connector.connector.build_settings") as p_settings,
        patch("kelvin_connector.connector.build_engine") as p_engine,
        patch("kelvin_connector.connector.build_kelvin_storage_session_factory") as p_storage,
        patch("kelvin_connector.connector.SynchronizationManager") as p_sync,
        patch("kelvin_connector.connector.AsyncioLoopThread") as p_loop,
    ):
        yield MagicMock(
            settings=p_settings,
            engine=p_engine,
            storage=p_storage,
            sync=p_sync,
            loop=p_loop,
            urlopen=urlopen,
        )


@pytest.mark.parametrize("server_type", [None, "backup"])
def test_build_runner_refuses_to_run_outside_the_primary(
    monkeypatch: pytest.MonkeyPatch, mocked_setup: MagicMock, server_type: str | None
) -> None:
    if server_type is None:
        monkeypatch.delenv("LDAP_SERVER_TYPE", raising=False)
    else:
        monkeypatch.setenv("LDAP_SERVER_TYPE", server_type)

    with pytest.raises(ConnectorSetupError, match="only runs on the Primary"):
        build_runner()
    mocked_setup.loop.return_value.start.assert_not_called()


@pytest.mark.parametrize("timeout", ["abc", "0", "-5"])
def test_build_runner_rejects_an_invalid_task_timeout(
    good_env: None, monkeypatch: pytest.MonkeyPatch, timeout: str
) -> None:
    monkeypatch.setenv("KELVIN_CONNECTOR_TASK_TIMEOUT", timeout)
    with pytest.raises(ConnectorSetupError, match="KELVIN_CONNECTOR_TASK_TIMEOUT"):
        build_runner()


def test_build_runner_propagates_invalid_db_settings(good_env: None) -> None:
    with patch("kelvin_connector.connector.build_settings", side_effect=RuntimeError("bad config")):
        with pytest.raises(RuntimeError, match="bad config"):
            build_runner()


def test_build_runner_waits_for_kelvin(good_env: None, mocked_setup: MagicMock) -> None:
    mocked_setup.urlopen.side_effect = OSError("connection refused")

    with pytest.raises(ConnectorSetupError, match="Kelvin is not ready yet"):
        build_runner()
    mocked_setup.loop.return_value.start.assert_not_called()


def test_build_runner_wires_the_sync_manager_and_starts_the_loop_thread(
    good_env: None, mocked_setup: MagicMock
) -> None:
    runner = build_runner()

    assert isinstance(runner, TaskRunner)
    assert mocked_setup.urlopen.call_args.args == (DEFAULT_KELVIN_HEALTH_URL,)
    mocked_setup.engine.assert_called_once_with(mocked_setup.settings.return_value)
    mocked_setup.storage.assert_called_once_with(mocked_setup.engine.return_value)
    mocked_setup.loop.return_value.start.assert_called_once_with()
    assert runner.loop_thread is mocked_setup.loop.return_value
    assert runner.processor.synchronization_manager is mocked_setup.sync.return_value
    assert runner.timeout == DEFAULT_TASK_TIMEOUT


def test_build_runner_reads_the_task_timeout_and_health_url(
    good_env: None, mocked_setup: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KELVIN_CONNECTOR_TASK_TIMEOUT", "12.5")
    monkeypatch.setenv("KELVIN_HEALTH_URL", "http://kelvin:8911/health")

    assert build_runner().timeout == 12.5
    assert mocked_setup.urlopen.call_args.args == ("http://kelvin:8911/health",)
