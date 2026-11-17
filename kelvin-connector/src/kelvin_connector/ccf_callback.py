# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
"""The CCF callback module (`PYTHON_CALLBACK=kelvin_connector.ccf_callback`).

Importing it only registers the functions with the CCF, which does not retry
a failed import. Everything that may fail and resolve itself later (Kelvin
not up yet) happens in `setup`, which the CCF retries until it succeeds.
"""

from ccf import CallbackResult, Consumer, Task, register

from kelvin_connector.connector import Connector, build_connector

_connector: Connector | None = None


@register.setup
def setup() -> None:
    global _connector
    # The CCF calls setup only until it succeeded once.
    _connector = build_connector()


@register.callback
def run(consumer: Consumer, task: Task) -> CallbackResult:
    if _connector is None:  # The CCF runs no task before setup succeeded.
        raise RuntimeError("the connector is not set up")
    return _connector.runner(consumer, task)


@register.shutdown
def shutdown() -> None:
    global _connector
    # The CCF calls shutdown only if setup succeeded.
    if _connector is not None:
        _connector.close()
        _connector = None
