from __future__ import annotations

import json
from pathlib import Path


def test_ari_fixture_parsing() -> None:
    fixture = json.loads(
        (Path(__file__).parent / "data" / "ari_channels_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert fixture["fixture"] == "ari_channels"
    assert fixture["version"] == 1
    assert fixture["data"][0]["id"] == "channel-A"
    assert fixture["data"][0]["caller"]["number"] == "user-A"
