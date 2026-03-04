import pytest

from telecom_mcp.authz import Mode, parse_mode, require_mode
from telecom_mcp.errors import NOT_ALLOWED, ToolError


def test_parse_mode_default() -> None:
    assert parse_mode(None) == Mode.INSPECT


def test_require_mode_allows_higher_mode() -> None:
    require_mode("x", Mode.EXECUTE_FULL, Mode.INSPECT)


def test_require_mode_denies_lower_mode() -> None:
    with pytest.raises(ToolError) as exc:
        require_mode("write.tool", Mode.INSPECT, Mode.EXECUTE_SAFE)
    assert exc.value.code == NOT_ALLOWED
