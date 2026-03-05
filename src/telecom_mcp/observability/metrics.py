"""Minimal in-process metrics instrumentation for telecom-mcp."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass(slots=True)
class MetricsRecorder:
    """Stores lightweight counters and latency samples for observability checks."""

    tool_latency_ms: dict[str, list[int]] = field(
        default_factory=lambda: defaultdict(list)
    )
    tool_error_count: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    connector_reconnect_count: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    tool_rate_limited_count: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )

    def record_tool_latency(self, tool_name: str, duration_ms: int) -> None:
        self.tool_latency_ms[tool_name].append(max(0, int(duration_ms)))

    def increment_tool_error(self, tool_name: str, error_code: str) -> None:
        self.tool_error_count[f"{tool_name}:{error_code}"] += 1

    def increment_connector_reconnect(self, connector: str, target_id: str) -> None:
        self.connector_reconnect_count[f"{connector}:{target_id}"] += 1

    def increment_tool_rate_limited(self, tool_name: str, scope: str) -> None:
        self.tool_rate_limited_count[f"{tool_name}:{scope}"] += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "tool_latency_ms": {k: list(v) for k, v in self.tool_latency_ms.items()},
            "tool_error_count": dict(self.tool_error_count),
            "connector_reconnect_count": dict(self.connector_reconnect_count),
            "tool_rate_limited_count": dict(self.tool_rate_limited_count),
        }
