from __future__ import annotations

import json
import os
import select
import subprocess
import sys


def _check_stdio_handshake() -> dict[str, object]:
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
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "mcp-sdk-smoke", "version": "1.0"},
            },
        }
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(initialize) + "\n")
        proc.stdin.flush()

        ready, _, _ = select.select([proc.stdout], [], [], 3.0)
        if not ready:
            return {"ok": False, "reason": "initialize_timeout"}
        init_line = proc.stdout.readline() if proc.stdout else ""
        try:
            init_payload = json.loads(init_line)
        except json.JSONDecodeError:
            return {
                "ok": False,
                "reason": "initialize_non_json",
                "line": init_line.strip(),
            }
        if init_payload.get("id") != 1:
            return {
                "ok": False,
                "reason": "initialize_bad_id",
                "payload": init_payload,
            }

        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                }
            )
            + "\n"
        )
        proc.stdin.flush()
        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                }
            )
            + "\n"
        )
        proc.stdin.flush()

        ready, _, _ = select.select([proc.stdout], [], [], 3.0)
        if not ready:
            return {"ok": False, "reason": "tools_list_timeout"}
        tools_line = proc.stdout.readline() if proc.stdout else ""
        try:
            tools_payload = json.loads(tools_line)
        except json.JSONDecodeError:
            return {
                "ok": False,
                "reason": "tools_list_non_json",
                "line": tools_line.strip(),
            }
        tool_names = [
            tool["name"] for tool in tools_payload.get("result", {}).get("tools", [])
        ]
        if "telecom.list_targets" not in tool_names:
            return {
                "ok": False,
                "reason": "required_tool_missing",
                "tool_count": len(tool_names),
            }
        return {"ok": True, "initialize_id": 1, "tool_count": len(tool_names)}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


def _check_stdio_liveness() -> dict[str, object]:
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
        return {"ok": True, "note": "process stayed alive in stdio mode for startup window"}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


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
    startup = _check_stdio_handshake()
    liveness = _check_stdio_liveness()
    flows = _check_tool_flows()

    print("STARTUP:", json.dumps(startup, sort_keys=True))
    print("LIVENESS:", json.dumps(liveness, sort_keys=True))
    print("FLOWS:", json.dumps(flows, sort_keys=True))

    ok = bool(startup.get("ok")) and bool(liveness.get("ok")) and bool(flows.get("ok"))
    if ok:
        print("SMOKE_OK")
        return 0
    print("SMOKE_FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
