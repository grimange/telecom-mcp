from __future__ import annotations

import json
from pathlib import Path


def test_esl_fixture_schema() -> None:
    fixture_dir = Path(__file__).resolve().parents[1] / "sanitized"
    fixtures = []
    for name in fixtures:
        payload = json.loads((fixture_dir / name).read_text(encoding="utf-8"))
        assert payload["version"] >= 1
        assert "data" in payload
