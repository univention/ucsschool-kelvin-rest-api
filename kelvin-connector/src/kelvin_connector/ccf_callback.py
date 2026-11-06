# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
"""The CCF callback module (`PYTHON_CALLBACK=kelvin_connector.ccf_callback`)."""

from typing import cast

from kelvin_connector.connector import build_runner
from kelvin_connector.tasks import CallbackResultClass, Task, to_callback_result

_runner = build_runner()


def run(_consumer: object, task: Task) -> object:
    # The CCF adds `CallbackResult` to this module's namespace after the import.
    callback_result = cast(CallbackResultClass, globals()["CallbackResult"])
    return to_callback_result(callback_result, _runner(task))
