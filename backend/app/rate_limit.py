"""Counts attempts inside a sliding time window, to slow down guessing.

Pure bookkeeping: it knows nothing about HTTP, log-ins or users. Whoever uses it chooses
what a "key" is (a username, a network address) and what counts as an attempt.

The counts live in this process's memory. They are lost on restart, and with several
server processes each would count separately. That is acceptable for what this guards
against, and matches how the app runs (one process).
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable


class AttemptLimiter:
    def __init__(
        self,
        max_attempts: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        # a clock that only moves forward; replaceable so tests need not wait
        self.clock = clock
        # key -> the times of its attempts still inside the window, oldest first
        self._attempts: dict[str, deque[float]] = {}
        self._last_sweep = clock()
        # routes run on several threads
        self._lock = threading.Lock()

    def seconds_until_allowed(self, key: str) -> int:
        """0 if this key may try now; otherwise how long until it may."""
        with self._lock:
            now = self.clock()
            attempts = self._still_counting(key, now)
            if len(attempts) < self.max_attempts:
                return 0
            # allowed again when the oldest attempt leaves the window
            return max(1, math.ceil(attempts[0] + self.window_seconds - now))

    def record(self, key: str) -> None:
        """Count one attempt for this key."""
        with self._lock:
            now = self.clock()
            self._still_counting(key, now).append(now)
            self._sweep_if_due(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._attempts)

    # ---- helpers; the caller holds the lock ----

    def _still_counting(self, key: str, now: float) -> deque[float]:
        """This key's attempts, with those older than the window dropped."""
        attempts = self._attempts.setdefault(key, deque())
        while attempts and attempts[0] <= now - self.window_seconds:
            attempts.popleft()
        return attempts

    def _sweep_if_due(self, now: float) -> None:
        """Once per window, forget every key with nothing left to count.

        Without this, attempts against endless made-up usernames would each leave a key
        behind and the dictionary would only ever grow.
        """
        if now - self._last_sweep < self.window_seconds:
            return
        self._last_sweep = now
        for key in list(self._attempts):
            if not self._still_counting(key, now):
                del self._attempts[key]
