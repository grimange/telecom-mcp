"""Secret leakage checks for chaos artifacts."""

from __future__ import annotations


SENSITIVE_MARKERS = ("password", "token", "secret", "authorization")


def detect_unredacted_secrets(text: str) -> list[str]:
    lower = text.lower()
    findings: list[str] = []
    for marker in SENSITIVE_MARKERS:
        if marker in lower and "***redacted***" not in lower:
            findings.append(marker)
    return sorted(set(findings))
