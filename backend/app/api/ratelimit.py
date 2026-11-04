"""A small in-memory rate limiter for the public applicant routes (SECURITY.md 4c).

It counts requests per key (a link id, a client address) in a sliding one-minute window. State
lives in the process: enough for one server in v1, and a restart only forgets the counts. The
clock can be replaced in tests. Keys are ids or addresses, never tokens.
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable

WINDOW_SECONDS = 60.0


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int) -> bool:
        """Record one request for `key`; False when it already made `limit` in the last minute."""
        now = self._clock()
        hits = self._hits[key]
        while hits and now - hits[0] > WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        if len(self._hits) > 5000:  # forget keys that went quiet
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > WINDOW_SECONDS]:
                del self._hits[k]
        return True
