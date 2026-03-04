"""STDIO MCP-like server dispatch for telecom-mcp."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .authz import Mode, parse_mode, require_mode
from .config import Settings, load_settings
from .envelope import build_envelope
from .errors import NOT_FOUND, VALIDATION_ERROR, ToolError, map_exception
from .logging import AuditLogger
from .tools import asterisk, freeswitch, telecom

ToolFunc = Callable[[Any, dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]]


@dataclass(slots=True)
class ServerContext:
    settings: Settings
    mode: Mode
    audit: AuditLogger
    server: "TelecomMCPServer"

    def call_tool_internal(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        return self.server.execute_tool(tool_name=tool_name, args=args, correlation_id=f"c-internal-{uuid.uuid4().hex[:8]}")


class TelecomMCPServer:
    def __init__(self, settings: Settings, *, mode: Mode | None = None, audit: AuditLogger | None = None) -> None:
        self.settings = settings
        self.mode = mode or settings.mode
        self.audit = audit or AuditLogger()
        self.tool_registry: dict[str, tuple[ToolFunc, Mode]] = {
            "telecom.list_targets": (telecom.list_targets, Mode.INSPECT),
            "telecom.summary": (telecom.summary, Mode.INSPECT),
            "telecom.capture_snapshot": (telecom.capture_snapshot, Mode.INSPECT),
            "asterisk.health": (asterisk.health, Mode.INSPECT),
            "asterisk.pjsip_show_endpoint": (asterisk.pjsip_show_endpoint, Mode.INSPECT),
            "asterisk.pjsip_show_endpoints": (asterisk.pjsip_show_endpoints, Mode.INSPECT),
            "asterisk.active_channels": (asterisk.active_channels, Mode.INSPECT),
            "freeswitch.health": (freeswitch.health, Mode.INSPECT),
            "freeswitch.sofia_status": (freeswitch.sofia_status, Mode.INSPECT),
            "freeswitch.channels": (freeswitch.channels, Mode.INSPECT),
        }

    def execute_tool(self, *, tool_name: str, args: dict[str, Any], correlation_id: str | None = None) -> dict[str, Any]:
        started = time.monotonic()
        correlation_id = correlation_id or f"c-{uuid.uuid4().hex[:12]}"
        pbx_id = args.get("pbx_id") if isinstance(args, dict) else None
        target = {"type": "telecom", "id": pbx_id or "unknown"}

        try:
            if tool_name not in self.tool_registry:
                raise ToolError(NOT_FOUND, f"Unknown tool: {tool_name}")

            tool_fn, minimum_mode = self.tool_registry[tool_name]
            require_mode(tool_name, self.mode, minimum_mode)
            ctx = ServerContext(settings=self.settings, mode=self.mode, audit=self.audit, server=self)
            target, data = tool_fn(ctx, args)
            duration_ms = int((time.monotonic() - started) * 1000)
            envelope = build_envelope(
                ok=True,
                target=target,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                data=data,
                error=None,
            )
            self.audit.log_tool_call(
                tool=tool_name,
                args=args,
                pbx_id=pbx_id,
                duration_ms=duration_ms,
                ok=True,
                correlation_id=correlation_id,
                error=None,
            )
            return envelope
        except Exception as exc:
            err = map_exception(exc)
            duration_ms = int((time.monotonic() - started) * 1000)
            envelope = build_envelope(
                ok=False,
                target=target,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                data={},
                error=err,
            )
            self.audit.log_tool_call(
                tool=tool_name,
                args=args,
                pbx_id=pbx_id,
                duration_ms=duration_ms,
                ok=False,
                correlation_id=correlation_id,
                error=err.to_dict(),
            )
            return envelope

    def handle_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        tool_name = payload.get("tool")
        args = payload.get("args", {})
        correlation_id = payload.get("correlation_id")

        if not isinstance(tool_name, str):
            raise ToolError(VALIDATION_ERROR, "Request missing 'tool' string")
        if not isinstance(args, dict):
            raise ToolError(VALIDATION_ERROR, "Request 'args' must be an object")

        return self.execute_tool(tool_name=tool_name, args=args, correlation_id=correlation_id)

    def run_stdio(self) -> None:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ToolError(VALIDATION_ERROR, "Request must be a JSON object")
                response = self.handle_request(payload)
            except Exception as exc:
                err = map_exception(exc)
                response = build_envelope(
                    ok=False,
                    target={"type": "telecom", "id": "unknown"},
                    duration_ms=0,
                    correlation_id=f"c-{uuid.uuid4().hex[:12]}",
                    data={},
                    error=err,
                )
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="telecom-mcp STDIO server")
    parser.add_argument("--targets-file", default="targets.yaml")
    parser.add_argument("--mode", default="inspect", choices=[m.value for m in Mode])
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    settings = load_settings(args.targets_file, mode=args.mode)
    server = TelecomMCPServer(settings=settings, mode=parse_mode(args.mode))
    server.run_stdio()
    return 0
