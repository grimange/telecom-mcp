"""Normalize sanitized telecom captures into versioned fixtures."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _parse_line_pairs(raw: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def _to_yaml_superset(payload: dict[str, Any]) -> str:
    # JSON is valid YAML 1.2 and avoids adding new dependencies.
    return json.dumps(payload, indent=2, sort_keys=True)


def normalize_sanitized_fixtures(
    *,
    sanitized_dir: Path,
    output_dir: Path,
    version: int = 1,
    captured_at: str | None = None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    capture_ts = (
        captured_at
        if captured_at
        else datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )

    for path in sorted(sanitized_dir.iterdir()):
        if not path.is_file():
            continue

        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            raw_text = path.read_text(encoding="utf-8")
            payload = {"raw_text": raw_text, "pairs": _parse_line_pairs(raw_text)}

        fixture = {
            "fixture": path.stem,
            "version": version,
            "captured_at": capture_ts,
            "source": path.name,
            "data": payload,
        }

        json_path = output_dir / f"{path.stem}_v{version}.json"
        yaml_path = output_dir / f"{path.stem}_v{version}.yaml"
        json_path.write_text(
            json.dumps(fixture, indent=2, sort_keys=True), encoding="utf-8"
        )
        yaml_path.write_text(_to_yaml_superset(fixture), encoding="utf-8")
        created.extend([json_path, yaml_path])

    return created
