# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import asyncio
import threading
from collections.abc import Coroutine
from typing import TypeVar

T = TypeVar("T")


class LoopThreadNotRunningError(RuntimeError):
    pass


class AsyncioLoopThread:
    """A long-lived asyncio event loop on a daemon thread.

    The CCF calls the callback synchronously on its worker threads, but the
    Kelvin DB is accessed through async SQLAlchemy, whose pooled connections
    are bound to the loop that opened them. One loop for the whole process
    keeps the connection pool usable across tasks.
    """

    def __init__(self, name: str = "kelvin-connector-loop") -> None:
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._thread: threading.Thread = threading.Thread(
            target=self._run_forever, name=name, daemon=True
        )

    def _run_forever(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def start(self) -> None:
        self._thread.start()

    def run(self, coro: Coroutine[object, object, T], timeout: float | None = None) -> T:
        """Run `coro` on the loop and block the calling thread until it is done.

        On timeout the coroutine is cancelled, so its transaction rolls back,
        and `TimeoutError` is raised.
        """
        if not self._thread.is_alive():
            coro.close()
            raise LoopThreadNotRunningError("the asyncio loop thread is not running")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout)
        except TimeoutError:
            future.cancel()
            raise

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()
