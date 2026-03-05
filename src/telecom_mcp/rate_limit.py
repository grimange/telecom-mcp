"""In-memory rate limiting primitives for write cooldown and burst control."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass(slots=True)
class CooldownStore:
    last_seen: dict[str, float] = field(default_factory=dict)

    def allowed(self, key: str, cooldown_seconds: int) -> bool:
        now = time.time()
        previous = self.last_seen.get(key)
        if previous is not None and now - previous < cooldown_seconds:
            return False
        self.last_seen[key] = now
        return True


@dataclass(slots=True)
class WindowRateLimiter:
    buckets: dict[str, deque[float]] = field(default_factory=dict)

    def allow(
        self, key: str, *, max_calls: int, window_seconds: float
    ) -> tuple[bool, int]:
        if max_calls <= 0 or window_seconds <= 0:
            return True, 0

        now = time.monotonic()
        bucket = self.buckets.setdefault(key, deque())
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= max_calls:
            return False, len(bucket)

        bucket.append(now)
        return True, len(bucket)
