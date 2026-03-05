from __future__ import annotations

import json
from pathlib import Path


def test_ami_fixture_parsing() -> None:
    fixture = json.loads(
        (Path(__file__).parent / "data" / "ami_pjsip_show_endpoints_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert fixture["fixture"] == "ami_pjsip_show_endpoints"
    assert fixture["version"] == 1
    assert fixture["data"]["ObjectName"] == "endpoint-A"
    assert fixture["data"]["Status"] == "Available"
