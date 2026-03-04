from telecom_mcp.envelope import build_envelope
from telecom_mcp.errors import ToolError, VALIDATION_ERROR


def test_build_envelope_success_shape() -> None:
    payload = build_envelope(
        ok=True,
        target={"type": "asterisk", "id": "pbx-1"},
        duration_ms=12,
        correlation_id="c-1",
        data={"x": 1},
    )
    assert payload["ok"] is True
    assert payload["target"] == {"type": "asterisk", "id": "pbx-1"}
    assert payload["duration_ms"] == 12
    assert payload["correlation_id"] == "c-1"
    assert payload["data"] == {"x": 1}
    assert payload["error"] is None
    assert "timestamp" in payload


def test_build_envelope_error_shape() -> None:
    err = ToolError(VALIDATION_ERROR, "bad args", {"field": "pbx_id"})
    payload = build_envelope(
        ok=False,
        target={"type": "telecom", "id": "unknown"},
        duration_ms=0,
        correlation_id="c-2",
        error=err,
    )
    assert payload["ok"] is False
    assert payload["error"]["code"] == VALIDATION_ERROR
