"""Mock ARI chaos scenarios."""

from __future__ import annotations

from collections.abc import Callable

from telecom_mcp.connectors.asterisk_ami import AsteriskAMIConnector
from telecom_mcp.connectors.asterisk_ari import AsteriskARIConnector
from telecom_mcp.errors import AUTH_FAILED, CONNECTION_FAILED, TIMEOUT, UPSTREAM_ERROR, ToolError

from ..injectors.faults import patched_attr


def run(
    run_tool: Callable[[str, dict], tuple[dict, str]],
) -> list[dict]:
    cases = [
        ("ARI_401_AUTH_ERROR", ToolError(AUTH_FAILED, "Injected ARI 401"), AUTH_FAILED),
        (
            "ARI_500_SERVER_ERROR",
            ToolError(UPSTREAM_ERROR, "Injected ARI 500"),
            UPSTREAM_ERROR,
        ),
        ("ARI_TIMEOUT", ToolError(TIMEOUT, "Injected ARI timeout"), TIMEOUT),
        (
            "ARI_WEBSOCKET_DROP",
            ToolError(CONNECTION_FAILED, "Injected ARI websocket drop"),
            CONNECTION_FAILED,
        ),
    ]
    results: list[dict] = []

    def _ami_ping_ok(*_args, **_kwargs):
        return {"ok": True, "latency_ms": 1, "response": {"Response": "Success"}}

    for name, exc, expected_code in cases:
        def _ari_health_fail(*_args, **_kwargs):
            raise exc

        with patched_attr(AsteriskAMIConnector, "ping", _ami_ping_ok), patched_attr(
            AsteriskARIConnector, "health", _ari_health_fail
        ):
            env, audit = run_tool("asterisk.health", {"pbx_id": "pbx-1"})

        results.append(
            {
                "scenario": name,
                "tool": "asterisk.health",
                "ok": env.get("ok") is False,
                "expected_error_code": expected_code,
                "actual_error_code": (env.get("error") or {}).get("code"),
                "envelope": env,
                "audit": audit,
            }
        )

    return results
