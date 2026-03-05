"""Rate limiting and backpressure chaos scenarios."""

from __future__ import annotations

import time
from collections.abc import Callable

from telecom_mcp.server import TelecomMCPServer


def run_burst(
    server: TelecomMCPServer,
    run_tool: Callable[[str, dict], tuple[dict, str]],
    *,
    calls: int = 500,
) -> dict:
    denied = 0
    allowed = 0
    durations_ms: list[int] = []

    for _ in range(calls):
        env, _ = run_tool("telecom.list_targets", {})
        durations_ms.append(int(env.get("duration_ms", 0)))
        if env.get("ok"):
            allowed += 1
        elif (env.get("error") or {}).get("code") == "NOT_ALLOWED":
            denied += 1

    return {
        "scenario": "burst_tool_calls",
        "requested_calls": calls,
        "allowed": allowed,
        "denied": denied,
        "rate_limit_active": denied > 0,
        "duration_ms": {
            "max": max(durations_ms) if durations_ms else 0,
            "avg": round(sum(durations_ms) / len(durations_ms), 2) if durations_ms else 0,
        },
        "server_limit": {
            "max_calls_per_window": server.settings.max_calls_per_window,
            "rate_limit_window_seconds": server.settings.rate_limit_window_seconds,
        },
    }


def run_slow_connector(
    run_tool: Callable[[str, dict], tuple[dict, str]],
) -> dict:
    started = time.monotonic()
    env, _ = run_tool("asterisk.health", {"pbx_id": "pbx-1"})
    elapsed_ms = int((time.monotonic() - started) * 1000)
    err_code = (env.get("error") or {}).get("code")

    return {
        "scenario": "slow_connector_simulation",
        "ok": env.get("ok", False),
        "error_code": err_code,
        "elapsed_ms": elapsed_ms,
        "expect_timeout": err_code == "TIMEOUT",
    }


def run_concurrency(
    run_tool: Callable[[str, dict], tuple[dict, str]],
    *,
    callers: int = 8,
    calls_per_caller: int = 50,
) -> dict:
    # Deterministic single-threaded simulation: callers are interleaved.
    latencies: list[int] = []
    denied = 0
    total = callers * calls_per_caller

    for idx in range(total):
        env, _ = run_tool("telecom.list_targets", {})
        latencies.append(int(env.get("duration_ms", 0)))
        if (env.get("error") or {}).get("code") == "NOT_ALLOWED":
            denied += 1

    avg = (sum(latencies) / len(latencies)) if latencies else 0
    bounded = max(latencies, default=0) <= max(avg * 10, 100)

    return {
        "scenario": "concurrent_tool_calls",
        "callers": callers,
        "calls_per_caller": calls_per_caller,
        "total_calls": total,
        "denied": denied,
        "fairness": "interleaved",
        "bounded_latency": bounded,
        "latency_ms": {
            "max": max(latencies) if latencies else 0,
            "avg": round(avg, 2),
        },
    }
