import os

import pytest

from telecom_mcp.config import load_settings, resolve_secret_env
from telecom_mcp.errors import AUTH_FAILED, NOT_FOUND, ToolError


def test_load_settings_and_get_target(tmp_path) -> None:
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

    settings = load_settings(config_file)
    target = settings.get_target("pbx-1")
    assert target.type == "asterisk"

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
