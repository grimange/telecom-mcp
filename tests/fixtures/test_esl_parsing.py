from __future__ import annotations

import json
from pathlib import Path


def test_esl_fixture_parsing() -> None:
    fixture = json.loads(
        (Path(__file__).parent / "data" / "esl_status_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert fixture["fixture"] == "esl_status"
    assert fixture["version"] == 1
    assert "UP" in fixture["data"]["raw_text"]
