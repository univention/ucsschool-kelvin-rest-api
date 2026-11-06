# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import asyncio
import threading

import pytest
from kelvin_connector.loop_thread import AsyncioLoopThread, LoopThreadNotRunningError


@pytest.fixture
def loop_thread():
    loop_thread = AsyncioLoopThread()
    loop_thread.start()
    yield loop_thread
    loop_thread.stop()


def test_run_returns_the_coroutine_result_computed_on_the_loop_thread(loop_thread):
    async def which_thread():
        await asyncio.sleep(0)
        return threading.current_thread().name

    assert loop_thread.run(which_thread()) == "kelvin-connector-loop"


def test_run_reuses_the_same_loop_across_calls(loop_thread):
    async def current_loop():
        return asyncio.get_running_loop()

    assert loop_thread.run(current_loop()) is loop_thread.run(current_loop())


def test_run_propagates_exceptions(loop_thread):
    async def fail():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        loop_thread.run(fail())


def test_run_cancels_the_coroutine_on_timeout(loop_thread):
    cancelled = threading.Event()

    async def hang():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with pytest.raises(TimeoutError):
        loop_thread.run(hang(), timeout=0.05)
    assert cancelled.wait(5)


def test_run_refuses_when_the_thread_is_not_running():
    loop_thread = AsyncioLoopThread()

    async def never_awaited():
        raise AssertionError("must not run")

    coro = never_awaited()
    with pytest.raises(LoopThreadNotRunningError):
        loop_thread.run(coro)
    assert coro.cr_frame is None, "the coroutine is closed instead of leaking"
