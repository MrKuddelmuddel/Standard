"""In-process sliding-window rate limiter. Per process only; use a shared store when running several API replicas."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from .errors import ApiError


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: float = 60.0) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_seconds:
                q.popleft()
            if len(q) >= limit:
                retry = int(window_seconds - (now - q[0])) + 1
                raise ApiError(
                    429, "rate_limited", f"Too many requests. Try again in {retry} seconds.", {"retry_after": retry}
                )
            q.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
