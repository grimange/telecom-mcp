from __future__ import annotations

import pytest

from telecom_mcp.connectors.asterisk_ami import AsteriskAMIConnector
from telecom_mcp.connectors.asterisk_ari import AsteriskARIConnector
from telecom_mcp.connectors.freeswitch_esl import FreeSWITCHESLConnector
from telecom_mcp.config import AMIConfig, ARIConfig, ESLConfig
from telecom_mcp.errors import CONNECTION_FAILED, TIMEOUT, ToolError


def test_ami_connection_error_maps() -> None:
    connector = AsteriskAMIConnector(AMIConfig(host="203.0.113.1", port=9, username_env="U", password_env="P"), timeout_s=0.01)
    with pytest.raises(ToolError) as exc:
        connector.connect()
    assert exc.value.code in {CONNECTION_FAILED, TIMEOUT}


def test_ari_missing_env_auth() -> None:
    connector = AsteriskARIConnector(ARIConfig(url="http://127.0.0.1:1", username_env="NO_USER", password_env="NO_PASS"), timeout_s=0.01)
    with pytest.raises(ToolError):
        connector.health()
    connector.close()


def test_esl_connection_error_maps() -> None:
    connector = FreeSWITCHESLConnector(ESLConfig(host="203.0.113.1", port=9, password_env="P"), timeout_s=0.01)
    with pytest.raises(ToolError) as exc:
        connector.connect()
    assert exc.value.code in {CONNECTION_FAILED, TIMEOUT}
