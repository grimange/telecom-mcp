from __future__ import annotations

import json
from pathlib import Path

import pytest

from telecom_mcp.config import load_settings
from telecom_mcp.errors import NOT_ALLOWED, ToolError
from telecom_mcp.fixtures.capture import FixtureCaptureRunner
from telecom_mcp.fixtures.normalizer import normalize_sanitized_fixtures
from telecom_mcp.fixtures.sanitizer import FixtureSanitizer


def _settings(tmp_path: Path, *, environment: str = "lab"):
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        f"""
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    environment: {environment}
    ari:
      url: http://10.0.0.10:8088
      username_env: AST_ARI_USER_PBX1
      password_env: AST_ARI_PASS_PBX1
      app: telecom_mcp
    ami:
      host: 10.0.0.10
      port: 5038
      username_env: AST_AMI_USER_PBX1
      password_env: AST_AMI_PASS_PBX1
""",
        encoding="utf-8",
    )
    return load_settings(config_file)


def test_fixture_sanitizer_masks_secrets_and_ips() -> None:
    sanitizer = FixtureSanitizer()
    raw = """Password: super-secret\nContact: sip:1001@192.168.1.10:5060\nCaller: +14155550123\n"""
    cleaned = sanitizer.sanitize_text(raw)
    assert "super-secret" not in cleaned
    assert "192.168.1.10" not in cleaned
    assert "+14155550123" not in cleaned
    sanitizer.assert_no_sensitive_markers(cleaned)


def test_normalize_sanitized_fixtures_writes_versioned_files(tmp_path: Path) -> None:
    sanitized_dir = tmp_path / "sanitized"
    output_dir = tmp_path / "out"
    sanitized_dir.mkdir()
    (sanitized_dir / "ari_channels.json").write_text(
        json.dumps([{"id": "channel-A"}]), encoding="utf-8"
    )

    created = normalize_sanitized_fixtures(
        sanitized_dir=sanitized_dir,
        output_dir=output_dir,
        version=2,
        captured_at="2026-03-05T00:00:00Z",
    )

    names = {path.name for path in created}
    assert "ari_channels_v2.json" in names
    assert "ari_channels_v2.yaml" in names


def test_fixture_capture_requires_lab_targets(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path, environment="prod")
    monkeypatch.setenv("FIXTURE_CAPTURE", "true")

    runner = FixtureCaptureRunner(settings, output_root=tmp_path / "fixtures")
    with pytest.raises(ToolError) as exc:
        runner.run()

    assert exc.value.code == NOT_ALLOWED


def test_fixture_capture_creates_report(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path, environment="lab")

    monkeypatch.setenv("FIXTURE_CAPTURE", "true")
    monkeypatch.setenv("AST_ARI_USER_PBX1", "ari-user")
    monkeypatch.setenv("AST_ARI_PASS_PBX1", "ari-pass")
    monkeypatch.setenv("AST_AMI_USER_PBX1", "ami-user")
    monkeypatch.setenv("AST_AMI_PASS_PBX1", "ami-pass")

    class FakeAMI:
        def __init__(self, *args, **kwargs):
            pass

        def send_action(self, action):
            return {"Action": action.get("Action"), "Status": "Available", "Contact": "sip:1001@10.1.1.1:5060"}

        def close(self):
            return None

    class FakeARI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, path):
            return [{"id": f"{path}-1", "caller": {"number": "+14155550123"}}]

        def close(self):
            return None

    monkeypatch.setattr("telecom_mcp.fixtures.capture.AsteriskAMIConnector", FakeAMI)
    monkeypatch.setattr("telecom_mcp.fixtures.capture.AsteriskARIConnector", FakeARI)

    runner = FixtureCaptureRunner(settings, output_root=tmp_path / "fixtures")
    report = runner.run()

    run_path = Path(report["run"])
    assert (run_path / "report.md").exists()
    assert report["phases"][-1]["phase"] == "F6"
