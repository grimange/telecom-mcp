"""Write tool guardrail chaos scenarios."""

from __future__ import annotations

from telecom_mcp.connectors.asterisk_ami import AsteriskAMIConnector
from telecom_mcp.config import load_settings
from telecom_mcp.server import TelecomMCPServer

from ..injectors.faults import patched_attr


WRITE_TOOL = "asterisk.reload_pjsip"


def run(targets_file: str) -> dict:
    inspect_server = TelecomMCPServer(load_settings(targets_file, mode="inspect"))
    execute_safe_server = TelecomMCPServer(load_settings(targets_file, mode="execute_safe"))
    cooldown_server = TelecomMCPServer(
        load_settings(
            targets_file,
            mode="execute_safe",
            write_allowlist=[WRITE_TOOL],
            cooldown_seconds=60,
        )
    )

    inspect_resp = inspect_server.execute_tool(
        tool_name=WRITE_TOOL, args={"pbx_id": "pbx-1"}, correlation_id="c-chaos-write-inspect"
    )
    allowlist_resp = execute_safe_server.execute_tool(
        tool_name=WRITE_TOOL, args={"pbx_id": "pbx-1"}, correlation_id="c-chaos-write-allowlist"
    )

    # First call is expected to fail here too because real network isn't available;
    # we only assert cooldown behavior on second invocation by code class.
    def _send_ok(*_args, **_kwargs):
        return {"Response": "Success", "Message": "Reloaded"}

    with patched_attr(AsteriskAMIConnector, "send_action", _send_ok):
        _first = cooldown_server.execute_tool(
            tool_name=WRITE_TOOL,
            args={"pbx_id": "pbx-1"},
            correlation_id="c-chaos-write-first",
        )
        second = cooldown_server.execute_tool(
            tool_name=WRITE_TOOL,
            args={"pbx_id": "pbx-1"},
            correlation_id="c-chaos-write-second",
        )

    return {
        "inspect_mode_write_blocked": {
            "ok": inspect_resp.get("ok"),
            "error_code": (inspect_resp.get("error") or {}).get("code"),
        },
        "allowlist_write_blocked": {
            "ok": allowlist_resp.get("ok"),
            "error_code": (allowlist_resp.get("error") or {}).get("code"),
        },
        "cooldown_blocked": {
            "ok": second.get("ok"),
            "error_code": (second.get("error") or {}).get("code"),
        },
    }
