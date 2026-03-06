"""Mock AMI chaos scenarios."""

from __future__ import annotations

from collections.abc import Callable

from telecom_mcp.connectors.asterisk_ami import AsteriskAMIConnector
from telecom_mcp.errors import (
    AUTH_FAILED,
    CONNECTION_FAILED,
    TIMEOUT,
    UPSTREAM_ERROR,
    ToolError,
)

from ..injectors.faults import patched_attr


def run(
    run_tool: Callable[[str, dict], tuple[dict, str]],
) -> list[dict]:
    cases = [
        ("AMI_TIMEOUT", ToolError(TIMEOUT, "Injected AMI timeout"), TIMEOUT),
        (
            "AMI_CONNECTION_DROP",
            ToolError(CONNECTION_FAILED, "Injected AMI connection drop"),
            CONNECTION_FAILED,
        ),
        (
            "AMI_AUTH_FAILURE",
            ToolError(AUTH_FAILED, "Injected AMI auth failure"),
            AUTH_FAILED,
        ),
        (
            "AMI_MALFORMED_RESPONSE",
            ToolError(UPSTREAM_ERROR, "Injected malformed AMI payload"),
            UPSTREAM_ERROR,
        ),
    ]
    results: list[dict] = []

    for name, exc, expected_code in cases:

        def _raise(*_args, **_kwargs):
            raise exc

        with patched_attr(AsteriskAMIConnector, "send_action", _raise):
            env, audit = run_tool("asterisk.pjsip_show_endpoints", {"pbx_id": "pbx-1"})
        results.append(
            {
                "scenario": name,
                "tool": "asterisk.pjsip_show_endpoints",
                "ok": env.get("ok") is False,
                "expected_error_code": expected_code,
                "actual_error_code": (env.get("error") or {}).get("code"),
                "envelope": env,
                "audit": audit,
            }
        )

    return results
