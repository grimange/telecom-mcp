"""Shared concurrency controls for active operations."""

from __future__ import annotations

import os
from collections import defaultdict
from contextlib import contextmanager
from threading import Lock
from typing import Iterator

from ..errors import NOT_ALLOWED, ToolError


class ActiveOperationController:
    """In-process active-operation concurrency guard.

    Guardrails are fail-closed and intended to prevent accidental saturation from
    concurrent active flows across probe/chaos/self-healing families.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._global_count = 0
        self._per_target_count: dict[str, int] = defaultdict(int)

    @staticmethod
    def _read_limit(env_key: str, default: int) -> int:
        raw = os.getenv(env_key, "").strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        return default

    @property
    def max_global(self) -> int:
        return self._read_limit("TELECOM_MCP_ACTIVE_MAX_GLOBAL", 4)

    @property
    def max_per_target(self) -> int:
        return self._read_limit("TELECOM_MCP_ACTIVE_MAX_PER_TARGET", 2)

    @contextmanager
    def guard(self, *, operation: str, pbx_id: str) -> Iterator[None]:
        acquired = False
        max_global = self.max_global
        max_per_target = self.max_per_target
        with self._lock:
            target_count = self._per_target_count[pbx_id]
            if self._global_count >= max_global or target_count >= max_per_target:
                raise ToolError(
                    NOT_ALLOWED,
                    "Active operation concurrency limit reached",
                    {
                        "operation": operation,
                        "pbx_id": pbx_id,
                        "max_global": max_global,
                        "max_per_target": max_per_target,
                        "active_global": self._global_count,
                        "active_for_target": target_count,
                        "policy_env": [
                            "TELECOM_MCP_ACTIVE_MAX_GLOBAL",
                            "TELECOM_MCP_ACTIVE_MAX_PER_TARGET",
                        ],
                    },
                )
            self._global_count += 1
            self._per_target_count[pbx_id] = target_count + 1
            acquired = True
        try:
            yield
        finally:
            if not acquired:
                return
            with self._lock:
                self._global_count = max(0, self._global_count - 1)
                next_count = max(0, self._per_target_count[pbx_id] - 1)
                if next_count:
                    self._per_target_count[pbx_id] = next_count
                else:
                    self._per_target_count.pop(pbx_id, None)


active_operation_controller = ActiveOperationController()
