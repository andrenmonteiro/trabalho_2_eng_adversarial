"""Simple spacing for sequential model calls under a per-minute request quota."""

from __future__ import annotations

import time
from collections.abc import Callable


class RequestPacer:
    def __init__(
        self,
        interval_seconds: float,
        *,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        if interval_seconds < 0:
            raise ValueError("interval_seconds cannot be negative")
        self.interval_seconds = interval_seconds
        self._clock = clock or time.monotonic
        self._sleep = sleeper or time.sleep
        self._last_request_at: float | None = None

    def wait_turn(self) -> float:
        """Wait if needed and return the number of seconds slept."""
        if self._last_request_at is None:
            self._last_request_at = self._clock()
            return 0.0

        elapsed = self._clock() - self._last_request_at
        delay = max(0.0, self.interval_seconds - elapsed)
        if delay:
            self._sleep(delay)
        self._last_request_at = self._clock()
        return delay

