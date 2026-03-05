"""Mock ESL chaos scenarios."""

from __future__ import annotations

from collections.abc import Callable

from telecom_mcp.connectors.freeswitch_esl import FreeSWITCHESLConnector
from telecom_mcp.errors import AUTH_FAILED, CONNECTION_FAILED, TIMEOUT, UPSTREAM_ERROR, ToolError

from ..injectors.faults import patched_attr


def run(
    run_tool: Callable[[str, dict], tuple[dict, str]],
) -> list[dict]:
    cases = [
        ("ESL_TIMEOUT", ToolError(TIMEOUT, "Injected ESL timeout"), TIMEOUT),
        (
            "ESL_CONNECTION_DROP",
            ToolError(CONNECTION_FAILED, "Injected ESL drop"),
            CONNECTION_FAILED,
        ),
        ("ESL_AUTH_FAILURE", ToolError(AUTH_FAILED, "Injected ESL auth failure"), AUTH_FAILED),
        (
            "ESL_MALFORMED_RESPONSE",
            ToolError(UPSTREAM_ERROR, "Injected ESL malformed response"),
            UPSTREAM_ERROR,
        ),
    ]
    results: list[dict] = []

    for name, exc, expected_code in cases:
        def _api_fail(*_args, **_kwargs):
            raise exc

        with patched_attr(FreeSWITCHESLConnector, "api", _api_fail):
            env, audit = run_tool("freeswitch.sofia_status", {"pbx_id": "fs-1"})

        results.append(
            {
                "scenario": name,
                "tool": "freeswitch.sofia_status",
                "ok": env.get("ok") is False,
                "expected_error_code": expected_code,
                "actual_error_code": (env.get("error") or {}).get("code"),
                "envelope": env,
                "audit": audit,
            }
        )

    return results
