# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from kelvin_connector.connector import DEFAULT_TASK_TIMEOUT, build_runner
from kelvin_connector.tasks import TaskRunner


@pytest.fixture
def good_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LDAP_SERVER_TYPE", "master")
    monkeypatch.delenv("KELVIN_CONNECTOR_TASK_TIMEOUT", raising=False)


@pytest.fixture
def mocked_setup() -> Iterator[MagicMock]:
    with (
        patch("kelvin_connector.connector.build_settings") as p_settings,
        patch("kelvin_connector.connector.build_engine") as p_engine,
        patch("kelvin_connector.connector.build_kelvin_storage_session_factory") as p_storage,
        patch("kelvin_connector.connector.SynchronizationManager") as p_sync,
        patch("kelvin_connector.connector.AsyncioLoopThread") as p_loop,
    ):
        yield MagicMock(
            settings=p_settings, engine=p_engine, storage=p_storage, sync=p_sync, loop=p_loop
        )


def test_build_runner_exits_when_ldap_server_type_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LDAP_SERVER_TYPE", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        build_runner()
    assert exc_info.value.code == 1


def test_build_runner_exits_when_ldap_server_type_is_not_master(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LDAP_SERVER_TYPE", "backup")
    with pytest.raises(SystemExit) as exc_info:
        build_runner()
    assert exc_info.value.code == 1


def test_build_runner_exits_when_unknown_log_level_is_present(
    good_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KELVIN_CONNECTOR_LOG_LEVEL", "DOESNOTEXIST")
    with pytest.raises(SystemExit) as exc_info:
        build_runner()
    assert exc_info.value.code == 1


@pytest.mark.parametrize("timeout", ["abc", "0", "-5"])
def test_build_runner_exits_when_task_timeout_is_invalid(
    good_env: None, monkeypatch: pytest.MonkeyPatch, timeout: str
) -> None:
    monkeypatch.setenv("KELVIN_CONNECTOR_TASK_TIMEOUT", timeout)
    with pytest.raises(SystemExit) as exc_info:
        build_runner()
    assert exc_info.value.code == 1


def test_build_runner_exits_when_build_settings_raises(good_env: None) -> None:
    with patch("kelvin_connector.connector.build_settings", side_effect=RuntimeError("bad config")):
        with pytest.raises(SystemExit) as exc_info:
            build_runner()
    assert exc_info.value.code == 1


def test_build_runner_wires_the_sync_manager_and_starts_the_loop_thread(
    good_env: None, mocked_setup: MagicMock
) -> None:
    runner = build_runner()

    assert isinstance(runner, TaskRunner)
    mocked_setup.engine.assert_called_once_with(mocked_setup.settings.return_value)
    mocked_setup.storage.assert_called_once_with(mocked_setup.engine.return_value)
    mocked_setup.loop.return_value.start.assert_called_once_with()
    assert runner.loop_thread is mocked_setup.loop.return_value
    assert runner.processor.synchronization_manager is mocked_setup.sync.return_value
    assert runner.timeout == DEFAULT_TASK_TIMEOUT


def test_build_runner_reads_the_task_timeout(
    good_env: None, mocked_setup: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KELVIN_CONNECTOR_TASK_TIMEOUT", "12.5")

    assert build_runner().timeout == 12.5
