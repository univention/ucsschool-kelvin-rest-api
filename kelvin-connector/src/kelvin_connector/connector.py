# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import os
import sys

from loguru import logger
from ucsschool_objects.core.adapters.sqlalchemy import (
    build_engine,
    build_kelvin_storage_session_factory,
    build_settings,
    sqlalchemy_mapper_factory,
)

from kelvin_connector.loop_thread import AsyncioLoopThread
from kelvin_connector.sync import SynchronizationManager
from kelvin_connector.tasks import TaskProcessor, TaskRunner

LOG_LEVELS = ("TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL")
LOG_FORMAT = (
    "{time:YYYY-MM-DDTHH:mm:ss.SSSSSSZ} {level: <8} [{extra[request_id]: >10}] {message}"
    "\t| module={name}:{line}"
)
DEFAULT_TASK_TIMEOUT = 300.0


def _configure_logging() -> None:
    level = os.environ.get("KELVIN_CONNECTOR_LOG_LEVEL", "DEBUG")
    if level not in LOG_LEVELS:
        logger.critical("Invalid log level provided: {}", level)
        sys.exit(1)
    logger.remove()
    logger.configure(extra={"request_id": "-"})
    # Bound at import time on purpose: the CCF swaps sys.stderr for its own
    # log capture during each callback call, and logs from the loop thread
    # must not end up in an unrelated call's capture.
    logger.add(sys.stderr, level=level, format=LOG_FORMAT)


def _task_timeout() -> float:
    raw = os.environ.get("KELVIN_CONNECTOR_TASK_TIMEOUT", str(DEFAULT_TASK_TIMEOUT))
    try:
        timeout = float(raw)
    except ValueError:
        timeout = 0.0
    if timeout <= 0:
        logger.critical("Invalid KELVIN_CONNECTOR_TASK_TIMEOUT provided: {}", raw)
        sys.exit(1)
    return timeout


def build_runner() -> TaskRunner:
    """Set up everything the CCF callback needs; exit on invalid configuration.

    Runs while the CCF imports the callback module, so a failure here stops
    the CCF before it fetches the first event.
    """
    _configure_logging()

    ldap_server_type = os.environ.get("LDAP_SERVER_TYPE")
    if ldap_server_type != "master":
        logger.critical(f"Connector cannot run on {ldap_server_type=}.")
        sys.exit(1)

    timeout = _task_timeout()

    try:
        settings = build_settings()
    except RuntimeError as e:
        logger.critical(str(e))
        sys.exit(1)

    engine = build_engine(settings)
    synchronization_manager = SynchronizationManager(
        storage_factory=build_kelvin_storage_session_factory(engine),
        mapper_factory=sqlalchemy_mapper_factory,
    )
    loop_thread = AsyncioLoopThread()
    loop_thread.start()
    return TaskRunner(loop_thread, TaskProcessor(synchronization_manager), timeout)
