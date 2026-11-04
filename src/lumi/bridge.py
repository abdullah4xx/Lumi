"""Runs asyncio in a background thread and hands results back to the GTK main loop."""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger("lumi.bridge")


class AsyncBridge:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="lumi-async", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro: Coroutine, on_done: Optional[Callable[[Any], None]] = None,
               on_error: Optional[Callable[[BaseException], None]] = None) -> Future:
        """Run ``coro`` on the async thread; callbacks are delivered on the GTK main thread."""
        from gi.repository import GLib

        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)

        def done(f: Future) -> None:
            try:
                result = f.result()
            except BaseException as exc:  # noqa: BLE001
                if on_error:
                    # bind `exc` now: Python deletes it when this except block ends,
                    # long before GLib runs the idle callback
                    GLib.idle_add(lambda e=exc: (on_error(e), False)[1])
                else:
                    logger.warning("background task failed: %s", exc)
                return
            if on_done:
                GLib.idle_add(lambda: (on_done(result), False)[1])

        fut.add_done_callback(done)
        return fut

    def call(self, coro: Coroutine, timeout: float = 5.0) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def shutdown(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
