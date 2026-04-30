from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine

from busylib.client import AsyncBusyBar


class AsyncRunner:
    """
    Run coroutines in a dedicated event loop thread.

    Starts a background loop and proxies coroutine execution with thread-safe calls.
    """

    def __init__(self) -> None:
        """
        Initialize runner with a fresh event loop and worker thread.

        Keeps thread state for start/stop orchestration.
        """
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._started = threading.Event()
        self._stopped = threading.Event()
        self.client: AsyncBusyBar | None = None

    def _run_loop(self) -> None:
        """
        Run the event loop until stopped.

        Used as the thread target to keep the loop alive in background.
        """
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()
        self._stopped.set()

    def start(self, client: AsyncBusyBar) -> None:
        """
        Start the loop thread and attach the client.

        Does nothing if the thread already runs.
        """
        if self._thread.is_alive():
            return
        self.client = client
        self._thread.start()
        self._started.wait()

    def stop(self) -> None:
        """
        Stop the background event loop thread.

        Signals the loop and waits briefly for termination.
        """
        if not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._stopped.wait(timeout=1)

    def run(self, coro: asyncio.Future | Coroutine) -> object:
        """
        Run a coroutine in the background loop and return its result.

        Ensures the runner is started and has an attached client.
        """
        if not self._thread.is_alive():
            raise RuntimeError("AsyncRunner not started")
        if self.client is None:
            raise RuntimeError("AsyncRunner client is not set")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def require_client(self) -> AsyncBusyBar:
        """
        Return the attached client or raise if missing.

        Useful for type checkers and safer access patterns.
        """
        if self.client is None:
            raise RuntimeError("AsyncRunner client is not set")
        return self.client
