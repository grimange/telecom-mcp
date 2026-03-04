from __future__ import annotations

import json

from telecom_mcp.config import load_settings
from telecom_mcp.errors import ALLOWED_ERROR_CODES
from telecom_mcp.server import TelecomMCPServer


def _make_settings(tmp_path):
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        """
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
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
  - id: fs-1
    type: freeswitch
    host: 10.0.0.20
    esl:
      host: 10.0.0.20
      port: 8021
      password_env: FS_ESL_PASS_FS1
""",
        encoding="utf-8",
    )
    return load_settings(config_file, mode="inspect")


def test_list_targets_envelope_contract(tmp_path) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)

    resp = server.execute_tool(tool_name="telecom.list_targets", args={}, correlation_id="c-test")

    for key in ("ok", "timestamp", "target", "duration_ms", "correlation_id", "data", "error"):
        assert key in resp
    assert resp["ok"] is True
    assert isinstance(resp["data"]["targets"], list)


def test_error_contract_has_standard_code(tmp_path) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)

    resp = server.execute_tool(tool_name="unknown.tool", args={}, correlation_id="c-test")

    assert resp["ok"] is False
    assert resp["error"]["code"] in ALLOWED_ERROR_CODES


def test_no_secret_leak_in_audit_redaction(tmp_path, capsys) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)

    _ = server.execute_tool(
        tool_name="telecom.list_targets",
        args={"password": "should-not-leak"},
        correlation_id="c-redact",
    )

    captured = capsys.readouterr().err
    assert "should-not-leak" not in captured
    assert "***REDACTED***" in captured


def test_mode_gating_pattern_for_unknown_read_tool(tmp_path) -> None:
    # Read tools are allowed in inspect; this checks server response shape in mode enforcement path indirectly.
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)
    resp = server.execute_tool(tool_name="telecom.list_targets", args={})
    assert resp["ok"] is True

    # Validate serialized form remains JSON-safe for MCP transport.
    json.dumps(resp)
