from __future__ import annotations

import json
import os
import subprocess
import sys


def _check_stdio_startup() -> dict[str, object]:
    env = os.environ.copy()
    env.setdefault("TELECOM_MCP_FIXTURES", "1")
    env.setdefault("TELECOM_MCP_ENABLE_REAL_PBX", "0")
    env.setdefault("TELECOM_MCP_TRANSPORT", "stdio")

    proc = subprocess.Popen(
        [sys.executable, "-m", "telecom_mcp.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    try:
        proc.wait(timeout=2)
        return {
            "ok": False,
            "exit_code": proc.returncode,
            "stderr": (proc.stderr.read() if proc.stderr else "").strip(),
        }
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait(timeout=2)
        return {
            "ok": True,
            "note": "process stayed alive in stdio mode for startup window",
        }


class _DummyMcp:
    def __init__(self, _name: str) -> None:
        self.tools = {}
        self.resources = {}
        self.prompts = {}

    def tool(self, name: str):
        def _decorator(fn):
            self.tools[name] = fn
            return fn

        return _decorator

    def resource(self, uri: str):
        def _decorator(fn):
            self.resources[uri] = fn
            return fn

        return _decorator

    def prompt(self, name: str):
        def _decorator(fn):
            self.prompts[name] = fn
            return fn

        return _decorator

    def run(self, **_kwargs) -> None:
        return None


def _check_tool_flows() -> dict[str, object]:
    from telecom_mcp.mcp_server import server as server_mod

    original = server_mod._import_mcp_server_class
    server_mod._import_mcp_server_class = lambda: _DummyMcp
    try:
        server = server_mod.TelecomMcpSdkServer(targets_file="targets.yaml", mode="inspect")

        names = sorted(server.app.tools.keys())
        required = {
            "telecom.healthcheck",
            "telecom.list_targets",
            "telecom.summary",
        }
        if not required.issubset(set(names)):
            return {"ok": False, "reason": "required tools missing", "tools": names}

        health = server.app.tools["telecom.healthcheck"]()
        listed = server.app.tools["telecom.list_targets"]()
        summary_ok = server.app.tools["telecom.summary"]("pbx-1")
        summary_invalid = server.app.tools["telecom.summary"]("")

        contract_payload = server.app.resources["contract://inbound-call/v0.1"]()
        json.loads(contract_payload)

        return {
            "ok": True,
            "tools": names,
            "health": health,
            "list_targets_ok": bool(listed.get("ok")),
            "summary_ok": summary_ok,
            "summary_invalid": summary_invalid,
        }
    finally:
        server_mod._import_mcp_server_class = original


def main() -> int:
    startup = _check_stdio_startup()
    flows = _check_tool_flows()

    print("STARTUP:", json.dumps(startup, sort_keys=True))
    print("FLOWS:", json.dumps(flows, sort_keys=True))

    ok = bool(startup.get("ok")) and bool(flows.get("ok"))
    if ok:
        print("SMOKE_OK")
        return 0
    print("SMOKE_FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
