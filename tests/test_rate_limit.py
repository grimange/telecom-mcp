from __future__ import annotations

from telecom_mcp.rate_limit import WindowRateLimiter


def test_window_rate_limiter_enforces_window() -> None:
    limiter = WindowRateLimiter()
    key = "telecom.list_targets:global"

    assert limiter.allow(key, max_calls=2, window_seconds=10)[0] is True
    assert limiter.allow(key, max_calls=2, window_seconds=10)[0] is True
    allowed, current = limiter.allow(key, max_calls=2, window_seconds=10)

    assert allowed is False
    assert current == 2
