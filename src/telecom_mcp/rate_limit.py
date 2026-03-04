"""Simple in-memory cooldown helper for future write tools."""

from __future__ import annotations

import time
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
