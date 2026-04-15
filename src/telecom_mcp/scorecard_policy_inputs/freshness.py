"""Freshness evaluation for scorecard policy input generation."""

from __future__ import annotations

from datetime import UTC, datetime


def _parse_iso8601(timestamp: str | None) -> datetime | None:
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None
    candidate = timestamp.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def evaluate_freshness(
    *,
    generated_at: str | None,
    stale_after_seconds: int = 2 * 60 * 60,
) -> tuple[str, list[str], bool]:
    parsed = _parse_iso8601(generated_at)
    if parsed is None:
        return (
            "unknown",
            ["Scorecard generated_at is missing or unparsable; evidence refresh required."],
            True,
        )
    now = datetime.now(UTC)
    age_seconds = max(0, int((now - parsed).total_seconds()))
    if age_seconds > stale_after_seconds:
        return (
            "stale",
            [
                f"Scorecard age {age_seconds}s exceeds stale threshold {stale_after_seconds}s.",
                "Stale scorecards cannot drive action-oriented recommendation handoff.",
            ],
            True,
        )
    return ("fresh", [f"Scorecard age is {age_seconds}s and within freshness threshold."], False)
