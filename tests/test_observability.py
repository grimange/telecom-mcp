from __future__ import annotations

import json

from telecom_mcp.config import load_settings
from telecom_mcp.logging import AuditLogger
from telecom_mcp.observability.metrics import MetricsRecorder
from telecom_mcp.server import TelecomMCPServer


def _make_settings(
    tmp_path, *, max_calls_per_window: int = 200, rate_limit_window_seconds: float = 1.0
):
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
""",
        encoding="utf-8",
    )
    return load_settings(
        config_file,
        mode="inspect",
        max_calls_per_window=max_calls_per_window,
        rate_limit_window_seconds=rate_limit_window_seconds,
    )


def test_audit_logger_structured_fields_and_redaction(capsys) -> None:
    audit = AuditLogger()
    audit.log_tool_call(
        tool="telecom.list_targets",
        args={"password": "super-secret", "pbx_id": "pbx-1"},
        pbx_id="pbx-1",
        duration_ms=8,
        ok=False,
        correlation_id="c-obs-test",
        error={"code": "NOT_ALLOWED", "message": "blocked", "details": {}},
    )

    row = json.loads(capsys.readouterr().err.strip())
    for key in (
        "timestamp",
        "level",
        "tool_name",
        "pbx_id",
        "correlation_id",
        "duration_ms",
        "ok",
        "error_code",
    ):
        assert key in row
    assert row["tool_name"] == "telecom.list_targets"
    assert row["error_code"] == "NOT_ALLOWED"
    assert row["args"]["password"] == "***REDACTED***"


def test_server_metrics_latency_error_and_rate_limit(tmp_path) -> None:
    settings = _make_settings(
        tmp_path,
        max_calls_per_window=1,
        rate_limit_window_seconds=60.0,
    )
    metrics = MetricsRecorder()
    server = TelecomMCPServer(settings=settings, metrics=metrics)

    _ = server.execute_tool(
        tool_name="telecom.list_targets", args={}, correlation_id="c-1"
    )
    _ = server.execute_tool(
        tool_name="telecom.list_targets", args={}, correlation_id="c-2"
    )
    _ = server.execute_tool(tool_name="unknown.tool", args={}, correlation_id="c-3")

    metrics.increment_connector_reconnect("asterisk_ami", "pbx-1")

    snap = metrics.snapshot()
    assert "telecom.list_targets" in snap["tool_latency_ms"]
    assert snap["tool_rate_limited_count"]["telecom.list_targets:global"] >= 1
    assert snap["tool_error_count"]["unknown.tool:NOT_FOUND"] >= 1
    assert snap["connector_reconnect_count"]["asterisk_ami:pbx-1"] == 1
