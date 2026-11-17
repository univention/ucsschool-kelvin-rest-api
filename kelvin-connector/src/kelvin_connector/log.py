# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
"""Logging glue for the CCF.

The CCF puts its own handler on the root logger before it imports the
callback and sets the level from its `LOG_LEVEL`, so the connector only uses
standard `logging`. The CCF knows a task's request ID on the thread it calls
the callback on; the asyncio loop thread doesn't have one, so records made
there get it from a context variable (an `extra` key the CCF reads).
"""

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar

# Below DEBUG; the CCF logs it as `trace`.
TRACE = 5

_request_id: ContextVar[str | None] = ContextVar("kelvin_connector_request_id", default=None)


@contextmanager
def request_id_context(request_id: str) -> Generator[None]:
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


class _RequestIdRecordFactory:
    """Adds the context's request ID to each record made within `request_id_context`."""

    def __init__(self, previous: Callable[..., logging.LogRecord]) -> None:
        self.previous: Callable[..., logging.LogRecord] = previous

    def __call__(self, *args: object, **kwargs: object) -> logging.LogRecord:
        record = self.previous(*args, **kwargs)
        request_id = _request_id.get()
        if request_id is not None:
            record.request_id = request_id
        return record


def install_request_id_record_factory() -> None:
    """Idempotent: the CCF repeats a failed setup, which imports the callback again."""
    factory = logging.getLogRecordFactory()
    if not isinstance(factory, _RequestIdRecordFactory):
        logging.setLogRecordFactory(_RequestIdRecordFactory(factory))
