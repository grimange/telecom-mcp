from __future__ import annotations

from types import SimpleNamespace

import pytest

from telecom_mcp.errors import NOT_ALLOWED, VALIDATION_ERROR, ToolError
from telecom_mcp.safety import (
    require_active_target_lab_safe,
    target_allows_active_validation,
    validate_probe_destination,
)


def test_target_allows_active_validation_only_for_explicit_lab_safe() -> None:
    allowed = SimpleNamespace(
        environment="lab",
        safety_tier="lab_safe",
        allow_active_validation=True,
    )
    blocked = SimpleNamespace(
        environment="prod",
        safety_tier="restricted",
        allow_active_validation=False,
    )

    assert target_allows_active_validation(allowed) is True
    assert target_allows_active_validation(blocked) is False


def test_require_active_target_lab_safe_fails_closed() -> None:
    blocked = SimpleNamespace(
        environment="prod",
        safety_tier="restricted",
        allow_active_validation=False,
    )

    with pytest.raises(ToolError) as exc:
        require_active_target_lab_safe(blocked, tool_name="test.active")

    assert exc.value.code == NOT_ALLOWED
    details = exc.value.details
    assert details["tool"] == "test.active"
    assert details["required"]["environment"] == "lab"


def test_validate_probe_destination_shared_policy() -> None:
    assert validate_probe_destination("1001") == "1001"

    with pytest.raises(ToolError) as exc:
        validate_probe_destination("1001; rm -rf /")

    assert exc.value.code == VALIDATION_ERROR
