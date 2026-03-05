from __future__ import annotations

import json
from pathlib import Path


def test_ami_fixture_schema() -> None:
    fixture_dir = Path(__file__).resolve().parents[2] / "sanitized"
    fixtures = ['ami_core_status.json', 'ami_core_status_v1.json', 'ami_pjsip_show_endpoint.json', 'ami_pjsip_show_endpoint_v1.json', 'ami_pjsip_show_endpoints.json', 'ami_pjsip_show_endpoints_v1.json']
    for name in fixtures:
        payload = json.loads((fixture_dir / name).read_text(encoding="utf-8"))
        assert payload["version"] >= 1
        assert "data" in payload
