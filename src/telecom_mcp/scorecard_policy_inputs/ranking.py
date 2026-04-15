"""Candidate ranking helpers for scorecard policy inputs."""

from __future__ import annotations

from typing import Any


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = [candidate for candidate in candidates if isinstance(candidate, dict)]
    ranked.sort(
        key=lambda item: (
            -int(item.get("priority", 0)),
            str(item.get("policy", "")),
        )
    )
    return ranked
