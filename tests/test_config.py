import pytest

from telecom_mcp.config import load_settings, resolve_secret_env
from telecom_mcp.errors import AUTH_FAILED, NOT_FOUND, VALIDATION_ERROR, ToolError
from telecom_mcp.server import run_cli


def test_load_settings_and_get_target(tmp_path) -> None:
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        """
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    environment: lab
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

    settings = load_settings(config_file)
    target = settings.get_target("pbx-1")
    assert target.type == "asterisk"
    assert target.environment == "lab"
    assert target.safety_tier == "standard"
    assert target.allow_active_validation is False

    with pytest.raises(ToolError) as exc:
        settings.get_target("missing")
    assert exc.value.code == NOT_FOUND


def test_resolve_secret_env_missing_raises(monkeypatch) -> None:
    key = "__DOES_NOT_EXIST__"
    monkeypatch.delenv(key, raising=False)
    with pytest.raises(ToolError) as exc:
        resolve_secret_env(key)
    assert exc.value.code == AUTH_FAILED


def test_resolve_secret_env_present(monkeypatch) -> None:
    monkeypatch.setenv("MY_SECRET", "abc")
    assert resolve_secret_env("MY_SECRET") == "abc"


def test_run_cli_startup_error_is_friendly(capsys) -> None:
    code = run_cli(["--targets-file", "/tmp/does-not-exist.yaml"])
    err = capsys.readouterr().err
    assert code == 2
    assert "startup_error code=VALIDATION_ERROR" in err


def test_load_settings_rejects_invalid_env_var_names(tmp_path) -> None:
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        """
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    ari:
      url: http://10.0.0.10:8088
      username_env: bad-name
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

    with pytest.raises(ToolError) as exc:
        load_settings(config_file)
    assert exc.value.code == VALIDATION_ERROR


def test_load_settings_accepts_active_validation_metadata(tmp_path) -> None:
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        """
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    environment: lab
    safety_tier: lab_safe
    allow_active_validation: true
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
    settings = load_settings(config_file)
    target = settings.get_target("pbx-1")
    assert target.environment == "lab"
    assert target.safety_tier == "lab_safe"
    assert target.allow_active_validation is True


def test_target_policy_enforcement_rejects_unknown_environment(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("TELECOM_MCP_ENFORCE_TARGET_POLICY", "1")
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
    with pytest.raises(ToolError) as exc:
        load_settings(config_file)
    assert exc.value.code == VALIDATION_ERROR
    assert "Target metadata policy validation failed" in exc.value.message


def test_target_policy_enforcement_rejects_unsafe_active_validation(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("TELECOM_MCP_ENFORCE_TARGET_POLICY", "1")
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        """
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    environment: production
    safety_tier: restricted
    allow_active_validation: true
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
    with pytest.raises(ToolError) as exc:
        load_settings(config_file)
    assert exc.value.code == VALIDATION_ERROR
    assert "Target metadata policy validation failed" in exc.value.message


def test_production_profile_requires_hardening_controls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_RUNTIME_PROFILE", "production")
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        """
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    environment: lab
    safety_tier: lab_safe
    allow_active_validation: true
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
    with pytest.raises(ToolError) as exc:
        load_settings(config_file)
    assert exc.value.code == VALIDATION_ERROR
    assert "Production runtime profile requires mandatory hardening controls" in exc.value.message


def test_production_profile_accepts_when_hardening_controls_enabled(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("TELECOM_MCP_RUNTIME_PROFILE", "production")
    monkeypatch.setenv("TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER", "1")
    monkeypatch.setenv("TELECOM_MCP_ENFORCE_TARGET_POLICY", "1")
    monkeypatch.setenv("TELECOM_MCP_STRICT_STATE_PERSISTENCE", "1")
    monkeypatch.setenv("TELECOM_MCP_AUTH_TOKEN", "token-123")
    monkeypatch.setenv(
        "TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES", "observability,validation,export"
    )
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        """
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    environment: lab
    safety_tier: lab_safe
    allow_active_validation: true
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
    settings = load_settings(config_file)
    assert settings.get_target("pbx-1").id == "pbx-1"


def test_production_profile_rejects_invalid_capability_classes(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("TELECOM_MCP_RUNTIME_PROFILE", "production")
    monkeypatch.setenv("TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER", "1")
    monkeypatch.setenv("TELECOM_MCP_ENFORCE_TARGET_POLICY", "1")
    monkeypatch.setenv("TELECOM_MCP_STRICT_STATE_PERSISTENCE", "1")
    monkeypatch.setenv("TELECOM_MCP_AUTH_TOKEN", "token-123")
    monkeypatch.setenv("TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES", "observability,invalid")
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        """
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    environment: lab
    safety_tier: lab_safe
    allow_active_validation: true
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
    with pytest.raises(ToolError) as exc:
        load_settings(config_file)
    assert exc.value.code == VALIDATION_ERROR
    assert "invalid capability class policy values" in exc.value.message


def test_hardened_profile_rejects_high_risk_classes_without_explicit_enable(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("TELECOM_MCP_RUNTIME_PROFILE", "production")
    monkeypatch.setenv("TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER", "1")
    monkeypatch.setenv("TELECOM_MCP_ENFORCE_TARGET_POLICY", "1")
    monkeypatch.setenv("TELECOM_MCP_STRICT_STATE_PERSISTENCE", "1")
    monkeypatch.setenv("TELECOM_MCP_AUTH_TOKEN", "token-123")
    monkeypatch.setenv(
        "TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES", "observability,chaos,remediation"
    )
    monkeypatch.delenv(
        "TELECOM_MCP_ENABLE_HIGH_RISK_CAPABILITY_CLASSES", raising=False
    )
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        """
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    environment: lab
    safety_tier: lab_safe
    allow_active_validation: true
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
    with pytest.raises(ToolError) as exc:
        load_settings(config_file)
    assert exc.value.code == VALIDATION_ERROR
    assert "High-risk capability classes require explicit runtime approval" in exc.value.message


def test_hardened_profile_allows_high_risk_classes_with_explicit_enable(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("TELECOM_MCP_RUNTIME_PROFILE", "production")
    monkeypatch.setenv("TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER", "1")
    monkeypatch.setenv("TELECOM_MCP_ENFORCE_TARGET_POLICY", "1")
    monkeypatch.setenv("TELECOM_MCP_STRICT_STATE_PERSISTENCE", "1")
    monkeypatch.setenv("TELECOM_MCP_AUTH_TOKEN", "token-123")
    monkeypatch.setenv(
        "TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES", "observability,chaos,remediation"
    )
    monkeypatch.setenv("TELECOM_MCP_ENABLE_HIGH_RISK_CAPABILITY_CLASSES", "1")
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        """
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    environment: lab
    safety_tier: lab_safe
    allow_active_validation: true
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
    settings = load_settings(config_file)
    assert settings.get_target("pbx-1").id == "pbx-1"


def test_pilot_profile_requires_hardening_controls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TELECOM_MCP_RUNTIME_PROFILE", "pilot")
    config_file = tmp_path / "targets.yaml"
    config_file.write_text(
        """
targets:
  - id: pbx-1
    type: asterisk
    host: 10.0.0.10
    environment: lab
    safety_tier: lab_safe
    allow_active_validation: true
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
    with pytest.raises(ToolError) as exc:
        load_settings(config_file)
    assert exc.value.code == VALIDATION_ERROR
    assert "Production runtime profile requires mandatory hardening controls" in exc.value.message
