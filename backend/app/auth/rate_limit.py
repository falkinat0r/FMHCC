"""Einfaches in-memory Rate-Limiting (frozen Semantik, R0).

Gilt fuer den Login-Endpoint pro Quell-IP (Sliding Window). Bewusst
simpel und transparent; bei mehreren Prozessen/Instanzen muessen die
Zaehler geteilt werden (offener Punkt, siehe foundation-handoff).
"""

from __future__ import annotations

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self._max_calls = max_calls
        self._window = window_seconds
        self._calls: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            window = self._calls.setdefault(key, deque())
            while window and now - window[0] > self._window:
                window.popleft()
            if len(window) >= self._max_calls:
                return False
            window.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._calls.clear()
