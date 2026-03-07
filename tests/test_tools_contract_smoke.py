from __future__ import annotations

import json

import pytest

from telecom_mcp.authz import Mode
from telecom_mcp.config import load_settings
from telecom_mcp.errors import (
    ALLOWED_ERROR_CODES,
    AUTH_FAILED,
    NOT_ALLOWED,
    VALIDATION_ERROR,
    ToolError,
)
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


def test_authenticated_caller_enforced(tmp_path, monkeypatch) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)
    monkeypatch.setenv("TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER", "1")
    monkeypatch.setenv("TELECOM_MCP_AUTH_TOKEN", "token-1")

    with pytest.raises(ToolError) as exc:
        server.handle_request({"tool": "telecom.list_targets", "args": {}})

    assert exc.value.code == AUTH_FAILED


def test_authenticated_caller_required_by_default(tmp_path, monkeypatch) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)
    monkeypatch.setenv("TELECOM_MCP_AUTH_TOKEN", "token-default")
    monkeypatch.delenv("TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER", raising=False)

    with pytest.raises(ToolError) as exc:
        server.handle_request({"tool": "telecom.list_targets", "args": {}})

    assert exc.value.code == AUTH_FAILED


def test_audit_log_includes_principal_fields(tmp_path, monkeypatch, capsys) -> None:
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)
    monkeypatch.setenv("TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER", "1")
    monkeypatch.setenv("TELECOM_MCP_AUTH_TOKEN", "token-2")
    monkeypatch.setenv("TELECOM_MCP_ALLOWED_CALLERS", "ops-bot")

    response = server.handle_request(
        {
            "tool": "telecom.list_targets",
            "args": {},
            "caller": "ops-bot",
            "auth": {"token": "token-2"},
        }
    )

    assert response["ok"] is True
    captured = capsys.readouterr().err
    assert '"principal":"ops-bot"' in captured
    assert '"principal_authenticated":true' in captured


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
        "telecom.baseline_create",
        "telecom.baseline_show",
        "telecom.audit_target",
        "telecom.drift_target_vs_baseline",
        "telecom.drift_compare_targets",
        "telecom.audit_report",
        "telecom.audit_export",
        "telecom.scorecard_target",
        "telecom.scorecard_cluster",
        "telecom.scorecard_environment",
        "telecom.scorecard_compare",
        "telecom.scorecard_trend",
        "telecom.scorecard_export",
        "telecom.scorecard_policy_inputs",
        "telecom.capture_incident_evidence",
        "telecom.generate_evidence_pack",
        "telecom.reconstruct_incident_timeline",
        "telecom.export_evidence_pack",
        "telecom.list_probes",
        "telecom.run_probe",
        "telecom.list_chaos_scenarios",
        "telecom.run_chaos_scenario",
        "telecom.list_self_healing_policies",
        "telecom.evaluate_self_healing",
        "telecom.run_self_healing_policy",
        "telecom.release_gate_decision",
        "telecom.release_promotion_decision",
        "telecom.release_gate_history",
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


def test_write_tool_requires_intent_metadata_in_execute_safe(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES",
        "observability,validation,remediation,chaos,export",
    )
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


@pytest.mark.parametrize(
    "wrapper_tool,destination",
    [
        ("telecom.run_registration_probe", "1001"),
        ("telecom.run_trunk_probe", "18005550199"),
    ],
)
def test_probe_wrapper_fails_closed_when_delegated_write_is_denied(
    tmp_path, monkeypatch, wrapper_tool: str, destination: str
) -> None:
    monkeypatch.setenv(
        "TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES",
        "observability,validation,remediation,chaos,export",
    )
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    settings = _make_settings_with_mode(
        tmp_path,
        mode="execute_safe",
        write_allowlist=[wrapper_tool],
        cooldown=0,
    )
    target = settings.get_target("pbx-1")
    target.environment = "lab"
    target.safety_tier = "lab_safe"
    target.allow_active_validation = True
    server = TelecomMCPServer(settings)

    response = server.execute_tool(
        tool_name=wrapper_tool,
        args={
            "pbx_id": "pbx-1",
            "destination": destination,
            "timeout_s": 10,
            "reason": "delegated write denied",
            "change_ticket": "CHG-3001",
        },
    )

    assert response["ok"] is False
    assert response["error"]["code"] == NOT_ALLOWED
    details = response["error"]["details"]
    assert details["delegated_tool"] == "asterisk.originate_probe"
    assert details["failed_sources"][0]["tool"] == "asterisk.originate_probe"


def test_probe_wrapper_executes_when_delegated_write_is_allowlisted(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv(
        "TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES",
        "observability,validation,remediation,chaos,export",
    )
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    monkeypatch.setenv("TELECOM_MCP_REQUIRE_CONFIRM_TOKEN", "1")
    monkeypatch.setenv("TELECOM_MCP_CONFIRM_TOKEN", "confirm-1")
    settings = _make_settings_with_mode(
        tmp_path,
        mode="execute_safe",
        write_allowlist=["telecom.run_registration_probe", "asterisk.originate_probe"],
        cooldown=0,
    )
    target = settings.get_target("pbx-1")
    target.environment = "lab"
    target.safety_tier = "lab_safe"
    target.allow_active_validation = True
    server = TelecomMCPServer(settings)

    seen_args: list[dict[str, object]] = []

    def _dummy_originate(ctx, args):
        seen_args.append(dict(args))
        return {"type": "asterisk", "id": "pbx-1"}, {"probe_id": "probe-ok", "initiated": True}

    server.tool_registry["asterisk.originate_probe"] = (_dummy_originate, Mode.EXECUTE_SAFE)

    response = server.execute_tool(
        tool_name="telecom.run_registration_probe",
        args={
            "pbx_id": "pbx-1",
            "destination": "1001",
            "timeout_s": 11,
            "reason": "delegated write allowed",
            "change_ticket": "CHG-3002",
            "confirm_token": "confirm-1",
        },
    )

    assert response["ok"] is True
    assert seen_args
    delegated_args = seen_args[0]
    assert delegated_args["reason"] == "delegated write allowed"
    assert delegated_args["change_ticket"] == "CHG-3002"
    assert delegated_args["confirm_token"] == "confirm-1"


def test_active_validation_smoke_propagates_write_intent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES",
        "observability,validation,remediation,chaos,export",
    )
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    settings = _make_settings_with_mode(
        tmp_path,
        mode="execute_safe",
        write_allowlist=["telecom.run_registration_probe"],
        cooldown=0,
    )
    target = settings.get_target("pbx-1")
    target.environment = "lab"
    target.safety_tier = "lab_safe"
    target.allow_active_validation = True
    server = TelecomMCPServer(settings)

    seen_args: list[dict[str, object]] = []

    def _dummy_run_registration_probe(ctx, args):
        seen_args.append(dict(args))
        return {"type": "asterisk", "id": "pbx-1"}, {"probe_id": "probe-active-smoke"}

    def _dummy_verify_cleanup(ctx, args):
        return {"type": "asterisk", "id": "pbx-1"}, {"clean": True}

    server.tool_registry["telecom.run_registration_probe"] = (
        _dummy_run_registration_probe,
        Mode.EXECUTE_SAFE,
    )
    server.tool_registry["telecom.verify_cleanup"] = (_dummy_verify_cleanup, Mode.INSPECT)

    response = server.execute_tool(
        tool_name="telecom.run_smoke_suite",
        args={
            "name": "active_validation_smoke",
            "pbx_id": "pbx-1",
            "params": {
                "destination": "1001",
                "reason": "smoke gate validation",
                "change_ticket": "CHG-3101",
                "confirm_token": "confirm-1",
            },
        },
    )

    assert response["ok"] is True
    assert seen_args
    delegated = seen_args[0]
    assert delegated["reason"] == "smoke gate validation"
    assert delegated["change_ticket"] == "CHG-3101"
    assert delegated["confirm_token"] == "confirm-1"


def test_active_validation_smoke_missing_write_intent_fails_closed(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv(
        "TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES",
        "observability,validation,remediation,chaos,export",
    )
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    settings = _make_settings_with_mode(tmp_path, mode="execute_safe", cooldown=0)
    target = settings.get_target("pbx-1")
    target.environment = "lab"
    target.safety_tier = "lab_safe"
    target.allow_active_validation = True
    server = TelecomMCPServer(settings)

    response = server.execute_tool(
        tool_name="telecom.run_smoke_suite",
        args={
            "name": "active_validation_smoke",
            "pbx_id": "pbx-1",
            "params": {"destination": "1001"},
        },
    )

    assert response["ok"] is False
    assert response["error"]["code"] == VALIDATION_ERROR


def test_active_probe_route_propagates_write_intent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES",
        "observability,validation,remediation,chaos,export",
    )
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    settings = _make_settings_with_mode(
        tmp_path,
        mode="execute_safe",
        write_allowlist=["telecom.run_registration_probe"],
        cooldown=0,
    )
    target = settings.get_target("pbx-1")
    target.environment = "lab"
    target.safety_tier = "lab_safe"
    target.allow_active_validation = True
    server = TelecomMCPServer(settings)

    seen_args: list[dict[str, object]] = []

    def _dummy_run_registration_probe(ctx, args):
        seen_args.append(dict(args))
        return {"type": "asterisk", "id": "pbx-1"}, {"probe_id": "probe-active-route"}

    def _dummy_logs(ctx, args):
        return {"type": "asterisk", "id": "pbx-1"}, {"items": [{"message": "probe evidence"}]}

    def _dummy_channels(ctx, args):
        return {"type": "asterisk", "id": "pbx-1"}, {"items": [{"channel_id": "PJSIP/1001-0001"}]}

    def _dummy_verify_cleanup(ctx, args):
        return {"type": "asterisk", "id": "pbx-1"}, {"clean": True}

    server.tool_registry["telecom.run_registration_probe"] = (
        _dummy_run_registration_probe,
        Mode.EXECUTE_SAFE,
    )
    server.tool_registry["telecom.logs"] = (_dummy_logs, Mode.INSPECT)
    server.tool_registry["telecom.channels"] = (_dummy_channels, Mode.INSPECT)
    server.tool_registry["telecom.verify_cleanup"] = (_dummy_verify_cleanup, Mode.INSPECT)

    response = server.execute_tool(
        tool_name="telecom.run_probe",
        args={
            "name": "controlled_originate_probe",
            "pbx_id": "pbx-1",
            "params": {
                "destination": "1001",
                "reason": "probe contract validation",
                "change_ticket": "CHG-3102",
            },
        },
    )

    assert response["ok"] is True
    assert seen_args
    delegated = seen_args[0]
    assert delegated["reason"] == "probe contract validation"
    assert delegated["change_ticket"] == "CHG-3102"


def test_capability_class_policy_blocks_validation_tools(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES", "observability,export")
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)

    response = server.execute_tool(tool_name="telecom.run_probe", args={})

    assert response["ok"] is False
    assert response["error"]["code"] == NOT_ALLOWED
    details = response["error"]["details"]
    assert details["tool"] == "telecom.run_probe"
    assert details["capability_class"] == "validation"
    assert details["policy_env"] == "TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES"


def test_default_capability_policy_denies_validation_outside_lab_profile(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES", raising=False)
    monkeypatch.delenv("TELECOM_MCP_RUNTIME_PROFILE", raising=False)
    settings = _make_settings(tmp_path)
    server = TelecomMCPServer(settings)

    response = server.execute_tool(tool_name="telecom.run_probe", args={})

    assert response["ok"] is False
    assert response["error"]["code"] == NOT_ALLOWED
    details = response["error"]["details"]
    assert details["tool"] == "telecom.run_probe"
    assert details["capability_class"] == "validation"
    assert details["allowed_capability_classes"] == ["observability"]


def test_non_mocked_orchestration_records_contract_failure_taxonomy(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv(
        "TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES",
        "observability,validation,remediation,chaos,export",
    )
    monkeypatch.setenv("TELECOM_MCP_ENABLE_ACTIVE_PROBES", "1")
    settings = _make_settings_with_mode(
        tmp_path,
        mode="execute_safe",
        write_allowlist=["telecom.run_registration_probe"],
        cooldown=0,
    )
    target = settings.get_target("pbx-1")
    target.environment = "lab"
    target.safety_tier = "lab_safe"
    target.allow_active_validation = True
    server = TelecomMCPServer(settings)

    response = server.execute_tool(
        tool_name="telecom.run_probe",
        args={
            "name": "controlled_originate_probe",
            "pbx_id": "pbx-1",
            "params": {
                "destination": "1001",
                "reason": "integration contract check",
                "change_ticket": "CHG-3201",
            },
        },
    )

    assert response["ok"] is True
    failed_sources = response["data"]["failed_sources"]
    assert any(
        row.get("tool") == "telecom.run_registration_probe"
        and row.get("contract_failure_reason") == "delegated_not_allowlisted"
        for row in failed_sources
        if isinstance(row, dict)
    )
    metrics = server.metrics.snapshot()["internal_subcall_contract_failure_count"]
    assert (
        metrics[
            "telecom.run_registration_probe->asterisk.originate_probe:delegated_not_allowlisted"
        ]
        >= 1
    )
