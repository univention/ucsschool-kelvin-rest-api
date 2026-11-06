# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
"""The CCF callback module (`PYTHON_CALLBACK=kelvin_connector.ccf_callback`)."""

from typing import Any

from kelvin_connector.connector import build_runner
from kelvin_connector.tasks import Task, to_callback_result

_runner = build_runner()


def run(_consumer: object, task: Task) -> Any:
    # The CCF adds `CallbackResult` to this module's namespace after the import.
    return to_callback_result(globals()["CallbackResult"], _runner(task))
