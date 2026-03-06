from __future__ import annotations

import json

import pytest

from telecom_mcp.authz import Mode
from telecom_mcp.config import load_settings
from telecom_mcp.errors import ALLOWED_ERROR_CODES, NOT_ALLOWED, VALIDATION_ERROR
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


def _make_settings_with_mode(tmp_path, *, mode: str, write_allowlist=None, cooldown=30):
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
        mode=mode,
        write_allowlist=write_allowlist or [],
        cooldown_seconds=cooldown,
    )


def test_list_targets_envelope_contract(tmp_path) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)

    resp = server.execute_tool(
        tool_name="telecom.list_targets", args={}, correlation_id="c-test"
    )

    for key in (
        "ok",
        "timestamp",
        "target",
        "duration_ms",
        "correlation_id",
        "data",
        "error",
    ):
        assert key in resp
    assert resp["ok"] is True
    assert isinstance(resp["data"]["targets"], list)


def test_error_contract_has_standard_code(tmp_path) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)

    resp = server.execute_tool(
        tool_name="unknown.tool", args={}, correlation_id="c-test"
    )

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


def test_registry_contains_spec_tools(tmp_path) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)
    expected = {
        "telecom.list_targets",
        "telecom.summary",
        "telecom.capture_snapshot",
        "telecom.endpoints",
        "telecom.registrations",
        "telecom.channels",
        "telecom.calls",
        "telecom.logs",
        "telecom.inventory",
        "telecom.diff_snapshots",
        "telecom.compare_targets",
        "telecom.run_smoke_test",
        "telecom.run_playbook",
        "telecom.run_smoke_suite",
        "telecom.assert_state",
        "telecom.run_registration_probe",
        "telecom.run_trunk_probe",
        "telecom.verify_cleanup",
        "asterisk.health",
        "asterisk.pjsip_show_endpoint",
        "asterisk.pjsip_show_endpoints",
        "asterisk.pjsip_show_registration",
        "asterisk.pjsip_show_contacts",
        "asterisk.active_channels",
        "asterisk.bridges",
        "asterisk.channel_details",
        "asterisk.core_show_channel",
        "asterisk.version",
        "asterisk.modules",
        "asterisk.logs",
        "asterisk.cli",
        "asterisk.originate_probe",
        "asterisk.reload_pjsip",
        "freeswitch.health",
        "freeswitch.sofia_status",
        "freeswitch.registrations",
        "freeswitch.gateway_status",
        "freeswitch.channels",
        "freeswitch.calls",
        "freeswitch.channel_details",
        "freeswitch.version",
        "freeswitch.modules",
        "freeswitch.logs",
        "freeswitch.api",
        "freeswitch.originate_probe",
        "freeswitch.reloadxml",
        "freeswitch.sofia_profile_rescan",
    }
    assert expected.issubset(set(server.tool_registry))


def test_write_tool_denied_in_inspect_mode(tmp_path) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)
    resp = server.execute_tool(
        tool_name="asterisk.reload_pjsip", args={"pbx_id": "pbx-1"}
    )
    assert resp["ok"] is False
    assert resp["error"]["code"] == NOT_ALLOWED


def test_write_tool_requires_allowlist(tmp_path) -> None:
    settings = _make_settings_with_mode(tmp_path, mode="execute_safe")
    server = TelecomMCPServer(settings)
    resp = server.execute_tool(
        tool_name="asterisk.reload_pjsip", args={"pbx_id": "pbx-1"}
    )
    assert resp["ok"] is False
    assert resp["error"]["code"] == NOT_ALLOWED


def test_failure_target_identity_uses_resolved_pbx_type(tmp_path) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)
    resp = server.execute_tool(
        tool_name="freeswitch.health",
        args={"pbx_id": "pbx-1"},
    )
    assert resp["ok"] is False
    assert resp["target"] == {"type": "asterisk", "id": "pbx-1"}


def test_write_tool_cooldown_enforced(tmp_path) -> None:
    settings = _make_settings_with_mode(
        tmp_path, mode="execute_safe", write_allowlist=["test.write"], cooldown=60
    )
    server = TelecomMCPServer(settings)

    def _dummy_write(ctx, args):
        return {"type": "telecom", "id": args.get("pbx_id", "n/a")}, {"ok": True}

    server.tool_registry["test.write"] = (_dummy_write, Mode.EXECUTE_SAFE)
    write_args = {
        "pbx_id": "pbx-1",
        "reason": "cooldown probe",
        "change_ticket": "CHG-1234",
    }
    first = server.execute_tool(tool_name="test.write", args=write_args)
    second = server.execute_tool(tool_name="test.write", args=write_args)

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["error"]["code"] == NOT_ALLOWED


def test_write_tool_requires_intent_metadata_in_execute_safe(tmp_path) -> None:
    settings = _make_settings_with_mode(
        tmp_path,
        mode="execute_safe",
        write_allowlist=["asterisk.reload_pjsip"],
    )
    server = TelecomMCPServer(settings)
    resp = server.execute_tool(
        tool_name="asterisk.reload_pjsip",
        args={"pbx_id": "pbx-1"},
    )
    assert resp["ok"] is False
    assert resp["error"]["code"] == VALIDATION_ERROR


def test_invalid_filter_argument_returns_validation_envelope(tmp_path) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)
    resp = server.execute_tool(
        tool_name="asterisk.pjsip_show_endpoints",
        args={"pbx_id": "pbx-1", "filter": "bad"},
    )
    assert resp["ok"] is False
    assert resp["error"]["code"] == VALIDATION_ERROR


def test_invalid_snapshot_include_returns_validation_envelope(tmp_path) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)
    resp = server.execute_tool(
        tool_name="telecom.capture_snapshot",
        args={"pbx_id": "pbx-1", "include": "bad"},
    )
    assert resp["ok"] is False
    assert resp["error"]["code"] == VALIDATION_ERROR


@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("asterisk.active_channels", {"pbx_id": "pbx-1", "limit": "abc"}),
        ("asterisk.bridges", {"pbx_id": "pbx-1", "limit": "abc"}),
        ("freeswitch.channels", {"pbx_id": "fs-1", "limit": "abc"}),
        ("freeswitch.calls", {"pbx_id": "fs-1", "limit": "abc"}),
        ("freeswitch.registrations", {"pbx_id": "fs-1", "limit": "abc"}),
    ],
)
def test_invalid_limit_argument_returns_validation_envelope(
    tmp_path, tool_name: str, args: dict[str, str]
) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)
    resp = server.execute_tool(tool_name=tool_name, args=args)
    assert resp["ok"] is False
    assert resp["error"]["code"] == VALIDATION_ERROR


def test_invalid_snapshot_limits_returns_validation_envelope(tmp_path) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)
    resp = server.execute_tool(
        tool_name="telecom.capture_snapshot",
        args={"pbx_id": "pbx-1", "limits": {"max_items": "bad"}},
    )
    assert resp["ok"] is False
    assert resp["error"]["code"] == VALIDATION_ERROR


def test_write_tool_requires_confirmation_token_when_configured(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("TELECOM_MCP_CONFIRM_TOKEN", "secret-1")
    settings = _make_settings_with_mode(
        tmp_path, mode="execute_safe", write_allowlist=["test.write"]
    )
    server = TelecomMCPServer(settings)

    def _dummy_write(ctx, args):
        return {"type": "telecom", "id": args.get("pbx_id", "n/a")}, {"ok": True}

    server.tool_registry["test.write"] = (_dummy_write, Mode.EXECUTE_SAFE)
    resp = server.execute_tool(
        tool_name="test.write",
        args={
            "pbx_id": "pbx-1",
            "reason": "token probe",
            "change_ticket": "CHG-2001",
        },
    )

    assert resp["ok"] is False
    assert resp["error"]["code"] == NOT_ALLOWED


def test_write_tool_requires_confirm_token_policy_profile(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("TELECOM_MCP_REQUIRE_CONFIRM_TOKEN", "1")
    settings = _make_settings_with_mode(
        tmp_path, mode="execute_safe", write_allowlist=["test.write"]
    )
    server = TelecomMCPServer(settings)

    def _dummy_write(ctx, args):
        return {"type": "telecom", "id": args.get("pbx_id", "n/a")}, {"ok": True}

    server.tool_registry["test.write"] = (_dummy_write, Mode.EXECUTE_SAFE)
    resp = server.execute_tool(
        tool_name="test.write",
        args={
            "pbx_id": "pbx-1",
            "reason": "policy probe",
            "change_ticket": "CHG-2002",
        },
    )

    assert resp["ok"] is False
    assert resp["error"]["code"] == NOT_ALLOWED
