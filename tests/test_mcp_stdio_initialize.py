from __future__ import annotations

import json
import importlib.util
import os
import select
import subprocess
import sys
import time

import pytest


_HAS_MCP = importlib.util.find_spec("mcp") is not None

def _read_line_with_timeout(stream, timeout: float) -> str | None:
    ready, _, _ = select.select([stream], [], [], timeout)
    if not ready:
        return None
    return stream.readline()


def test_stdio_initialize_and_list_tools_roundtrip() -> None:
    if not _HAS_MCP:
        pytest.skip("mcp package not installed in current test runtime")
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", "src")
    env.setdefault("TELECOM_MCP_TRANSPORT", "stdio")
    env.setdefault("TELECOM_MCP_FIXTURES", "1")
    env.setdefault("TELECOM_MCP_ENABLE_REAL_PBX", "0")

    proc = subprocess.Popen(
        [sys.executable, "-m", "telecom_mcp.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=".",
        bufsize=1,
    )
    try:
        assert _read_line_with_timeout(proc.stdout, 0.2) is None

        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "pytest-probe", "version": "1.0"},
            },
        }
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(initialize) + "\n")
        proc.stdin.flush()

        init_line = _read_line_with_timeout(proc.stdout, 3.0)
        assert init_line is not None
        init_payload = json.loads(init_line)
        assert init_payload["id"] == 1
        assert init_payload["result"]["serverInfo"]["name"] == "telecom-mcp"

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

        tools_line = _read_line_with_timeout(proc.stdout, 3.0)
        assert tools_line is not None
        tools_payload = json.loads(tools_line)
        assert tools_payload["id"] == 2
        tool_names = [tool["name"] for tool in tools_payload["result"]["tools"]]
        assert "telecom.list_targets" in tool_names
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1.0)


def test_stdio_with_devnull_stdin_has_no_traceback_noise() -> None:
    if not _HAS_MCP:
        pytest.skip("mcp package not installed in current test runtime")
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", "src")
    env.setdefault("TELECOM_MCP_TRANSPORT", "stdio")
    env.setdefault("TELECOM_MCP_FIXTURES", "1")
    env.setdefault("TELECOM_MCP_ENABLE_REAL_PBX", "0")

    proc = subprocess.Popen(
        [sys.executable, "-m", "telecom_mcp.mcp_server"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=".",
        bufsize=1,
    )
    try:
        time.sleep(0.4)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1.0)

    assert proc.stderr is not None
    stderr_output = proc.stderr.read()
    assert "Traceback" not in stderr_output
