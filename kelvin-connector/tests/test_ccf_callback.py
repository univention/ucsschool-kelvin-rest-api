# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import ccf
import pytest
from ccf import CallbackResult
from kelvin_connector import ccf_callback
from kelvin_connector.connector import ConnectorSetupError


@pytest.fixture
def connector() -> Iterator[MagicMock]:
    with patch.object(ccf_callback, "build_connector") as p_build:
        yield p_build.return_value
    ccf_callback._connector = None  # pyright: ignore[reportPrivateUsage]


def test_the_module_registers_its_functions_with_the_ccf() -> None:
    registry = ccf.register
    assert registry._callback is ccf_callback.run  # pyright: ignore[reportPrivateUsage]
    assert registry._setup is ccf_callback.setup  # pyright: ignore[reportPrivateUsage]
    assert registry._shutdown is ccf_callback.shutdown  # pyright: ignore[reportPrivateUsage]


def test_run_refuses_to_run_before_setup() -> None:
    consumer, task = MagicMock(), MagicMock()
    with pytest.raises(RuntimeError, match="not set up"):
        ccf_callback.run(consumer, task)


def test_a_failed_setup_leaves_the_connector_unset() -> None:
    with patch.object(
        ccf_callback, "build_connector", side_effect=ConnectorSetupError("Kelvin is not ready yet")
    ):
        with pytest.raises(ConnectorSetupError):
            ccf_callback.setup()

    assert ccf_callback._connector is None  # pyright: ignore[reportPrivateUsage]


def test_run_hands_the_task_to_the_runner_after_setup(connector: MagicMock) -> None:
    consumer, task = MagicMock(), MagicMock()
    connector.runner.return_value = CallbackResult.SuccessSkipped

    ccf_callback.setup()

    assert ccf_callback.run(consumer, task) == CallbackResult.SuccessSkipped
    connector.runner.assert_called_once_with(consumer, task)


def test_shutdown_closes_the_connector(connector: MagicMock) -> None:
    ccf_callback.setup()

    ccf_callback.shutdown()

    connector.close.assert_called_once_with()
    assert ccf_callback._connector is None  # pyright: ignore[reportPrivateUsage]


def test_shutdown_without_a_connector_does_nothing(connector: MagicMock) -> None:
    ccf_callback.shutdown()

    connector.close.assert_not_called()
