"""Audit log validators for chaos evidence."""

from __future__ import annotations

import json


def parse_jsonl_lines(raw_text: str) -> list[dict]:
    rows: list[dict] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def validate_audit_rows(rows: list[dict]) -> list[str]:
    issues: list[str] = []
    for idx, row in enumerate(rows, start=1):
        for key in ("tool", "duration_ms", "ok", "correlation_id"):
            if key not in row:
                issues.append(f"line_{idx}:missing_{key}")
    return issues
