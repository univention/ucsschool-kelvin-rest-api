# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import os
import urllib.request

from ucsschool_objects.core.adapters.sqlalchemy import (
    build_engine,
    build_kelvin_storage_session_factory,
    build_settings,
    sqlalchemy_mapper_factory,
)

from kelvin_connector.log import install_request_id_record_factory
from kelvin_connector.loop_thread import AsyncioLoopThread
from kelvin_connector.sync import SynchronizationManager
from kelvin_connector.tasks import TaskProcessor, TaskRunner

DEFAULT_TASK_TIMEOUT = 300.0
DEFAULT_KELVIN_HEALTH_URL = "http://api:8911/health"
KELVIN_HEALTH_TIMEOUT = 5.0


class ConnectorSetupError(RuntimeError):
    """The connector cannot start (yet); the CCF logs it and retries the setup."""


def _task_timeout() -> float:
    raw = os.environ.get("KELVIN_CONNECTOR_TASK_TIMEOUT", str(DEFAULT_TASK_TIMEOUT))
    try:
        timeout = float(raw)
    except ValueError:
        timeout = 0.0
    if timeout <= 0:
        raise ConnectorSetupError(f"Invalid KELVIN_CONNECTOR_TASK_TIMEOUT provided: {raw}")
    return timeout


def _require_kelvin_ready() -> None:
    """Kelvin migrates the Kelvin DB on start; it must be done before any write."""
    url = os.environ.get("KELVIN_HEALTH_URL", DEFAULT_KELVIN_HEALTH_URL)
    try:
        with urllib.request.urlopen(url, timeout=KELVIN_HEALTH_TIMEOUT):  # noqa: S310 -- configured URL
            pass
    except OSError as exc:
        raise ConnectorSetupError(f"Kelvin is not ready yet ({url}): {exc}") from exc


def build_runner() -> TaskRunner:
    """Set up everything the CCF callback needs.

    Runs while the CCF imports the callback module, before it fetches the
    first event. A `ConnectorSetupError` (or any other exception) makes the
    CCF log it and retry the import later, so the container stays up.
    """
    # Logging needs no setup: the CCF routes the root logger into its log
    # (level: the CCF's LOG_LEVEL).
    install_request_id_record_factory()

    ldap_server_type = os.environ.get("LDAP_SERVER_TYPE")
    if ldap_server_type != "master":
        raise ConnectorSetupError(f"The connector only runs on the Primary, not on {ldap_server_type=}")

    timeout = _task_timeout()
    settings = build_settings()
    _require_kelvin_ready()

    engine = build_engine(settings)
    synchronization_manager = SynchronizationManager(
        storage_factory=build_kelvin_storage_session_factory(engine),
        mapper_factory=sqlalchemy_mapper_factory,
    )
    loop_thread = AsyncioLoopThread()
    loop_thread.start()
    return TaskRunner(loop_thread, TaskProcessor(synchronization_manager), timeout)
