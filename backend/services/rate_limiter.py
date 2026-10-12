"""In-memory sliding-window rate limiter keyed by client IP."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict

WINDOW_SECONDS = 60.0


class SlidingWindowLimiter:
    def __init__(self, limit_per_window: int) -> None:
        self.limit = limit_per_window
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True
