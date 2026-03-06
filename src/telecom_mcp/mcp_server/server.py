"""MCP Python SDK server integration for telecom-mcp."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from telecom_mcp.authz import Mode, parse_mode
from telecom_mcp.config import Settings, load_settings
from telecom_mcp.envelope import build_envelope
from telecom_mcp.errors import ToolError
from telecom_mcp.mcp_server.runtime import RuntimeFlags, iso8601_now, load_runtime_flags
from telecom_mcp.server import TelecomMCPServer


def _import_mcp_server_class() -> type[Any]:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore

        return FastMCP
    except Exception:
        from mcp.server import MCPServer  # type: ignore

        return MCPServer


def _latest_audit_file() -> Path | None:
    root = Path("docs/audit/mcp-python-sdk-integration")
    if not root.exists():
        return None
    matches = sorted(root.glob("*--decision-record.md"))
    if not matches:
        return None
    return matches[-1]


def _resolve_targets_file(explicit: str | None) -> Path | None:
    candidates: list[Path] = []

    if explicit:
        candidates.append(Path(explicit))

    env_path = os.getenv("TELECOM_MCP_TARGETS_FILE", "").strip()
    if env_path:
        candidates.append(Path(env_path))

    repo_root = Path(__file__).resolve().parents[3]
    candidates.extend(
        [
            Path.cwd() / "targets.yaml",
            repo_root / "targets.yaml",
            repo_root / "config" / "targets.yaml",
            Path.home() / ".config" / "telecom-mcp" / "targets.yaml",
        ]
    )

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


class TelecomMcpSdkServer:
    def __init__(
        self,
        *,
        runtime_flags: RuntimeFlags | None = None,
        targets_file: str | None = None,
        mode: str = "inspect",
        write_allowlist: list[str] | None = None,
    ) -> None:
        self.runtime_flags = runtime_flags or load_runtime_flags()
        self.started_at = iso8601_now()
        self.startup_warnings: list[dict[str, Any]] = []

        self.mode = parse_mode(mode)
        self.settings = self._build_settings(
            targets_file=targets_file,
            mode=self.mode,
            write_allowlist=write_allowlist or [],
        )
        self.core_server = TelecomMCPServer(settings=self.settings, mode=self.mode)

        mcp_class = _import_mcp_server_class()
        self.app = mcp_class("telecom-mcp")
        self._register_tools()
        self._register_resources()
        self._register_prompts()

    def _build_settings(
        self, *, targets_file: str | None, mode: Mode, write_allowlist: list[str]
    ) -> Settings:
        self._append_targets_file_hygiene_warnings()
        resolved_targets = _resolve_targets_file(targets_file)
        if resolved_targets is None:
            self.startup_warnings.append(
                {
                    "code": "TARGETS_FILE_NOT_FOUND",
                    "message": "No targets.yaml found; starting with empty target catalog.",
                    "details": {
                        "requested": targets_file,
                        "env": os.getenv("TELECOM_MCP_TARGETS_FILE"),
                    },
                }
            )
            return Settings(targets=[], mode=mode, write_allowlist=write_allowlist)
        try:
            return load_settings(
                resolved_targets,
                mode=mode.value,
                write_allowlist=write_allowlist,
            )
        except ToolError as exc:
            self.startup_warnings.append(
                {
                    "code": exc.code,
                    "message": exc.message,
                    "details": {
                        "targets_file": str(resolved_targets),
                        "tool_error": exc.to_dict(),
                    },
                }
            )
            return Settings(targets=[], mode=mode, write_allowlist=write_allowlist)

    def _append_targets_file_hygiene_warnings(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        primary = repo_root / "targets.yaml"
        alternate = repo_root / "config" / "targets.yaml"
        if not primary.exists() or not alternate.exists():
            return
        warning: dict[str, Any] = {
            "code": "TARGETS_FILE_DUPLICATE",
            "message": "Multiple repository targets files detected; prefer repository-root targets.yaml as canonical.",
            "details": {
                "canonical": str(primary),
                "duplicate": str(alternate),
            },
        }
        try:
            if primary.read_text(encoding="utf-8") != alternate.read_text(
                encoding="utf-8"
            ):
                warning["details"]["drift"] = True
                warning["message"] = (
                    "Multiple repository targets files detected with different contents; "
                    "use a single canonical targets.yaml file."
                )
            else:
                warning["details"]["drift"] = False
        except OSError:
            warning["details"]["drift"] = "unknown"
        self.startup_warnings.append(warning)

    def _execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        return self.core_server.execute_tool(tool_name=tool_name, args=args)

    def _healthcheck_envelope(self) -> dict[str, Any]:
        started = time.monotonic()
        correlation_id = f"c-health-{uuid.uuid4().hex[:10]}"
        data = {
            "server": "telecom-mcp",
            "mode": self.mode.value,
            "transport": self.runtime_flags.transport,
            "fixtures": self.runtime_flags.fixtures,
            "real_backend": self.runtime_flags.real_pbx,
            "targets_count": len(self.settings.targets),
            "startup_warnings": self.startup_warnings,
        }
        duration_ms = int((time.monotonic() - started) * 1000)
        return build_envelope(
            ok=True,
            target={"type": "telecom", "id": "server"},
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            data=data,
            error=None,
        )

    def _register_tools(self) -> None:
        @self.app.tool(name="telecom.healthcheck")
        def telecom_healthcheck() -> dict[str, Any]:
            """Return server runtime status and startup diagnostics."""
            return self._healthcheck_envelope()

        @self.app.tool(name="telecom.list_targets")
        def telecom_list_targets() -> dict[str, Any]:
            """List configured telecom targets."""
            return self._execute("telecom.list_targets", {})

        @self.app.tool(name="telecom.summary")
        def telecom_summary(pbx_id: str) -> dict[str, Any]:
            """Return normalized one-call summary for a target."""
            return self._execute("telecom.summary", {"pbx_id": pbx_id})

        @self.app.tool(name="telecom.capture_snapshot")
        def telecom_capture_snapshot(
            pbx_id: str,
            include: dict[str, Any] | None = None,
            limits: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Capture bounded troubleshooting evidence for a target."""
            args: dict[str, Any] = {"pbx_id": pbx_id}
            if isinstance(include, dict):
                args["include"] = include
            if isinstance(limits, dict):
                args["limits"] = limits
            return self._execute("telecom.capture_snapshot", args)

        @self.app.tool(name="asterisk.health")
        def asterisk_health(pbx_id: str) -> dict[str, Any]:
            """Check AMI/ARI health for an Asterisk target."""
            return self._execute("asterisk.health", {"pbx_id": pbx_id})

        @self.app.tool(name="asterisk.pjsip_show_endpoint")
        def asterisk_pjsip_show_endpoint(pbx_id: str, endpoint: str) -> dict[str, Any]:
            """Inspect one PJSIP endpoint."""
            return self._execute(
                "asterisk.pjsip_show_endpoint",
                {"pbx_id": pbx_id, "endpoint": endpoint},
            )

        @self.app.tool(name="asterisk.pjsip_show_endpoints")
        def asterisk_pjsip_show_endpoints(
            pbx_id: str,
            filter: dict[str, Any] | None = None,
            limit: int = 200,
        ) -> dict[str, Any]:
            """List PJSIP endpoints with optional filters."""
            args: dict[str, Any] = {"pbx_id": pbx_id, "limit": limit}
            if isinstance(filter, dict):
                args["filter"] = filter
            return self._execute("asterisk.pjsip_show_endpoints", args)

        @self.app.tool(name="asterisk.pjsip_show_registration")
        def asterisk_pjsip_show_registration(
            pbx_id: str,
            registration: str,
        ) -> dict[str, Any]:
            """Inspect one outbound PJSIP registration."""
            return self._execute(
                "asterisk.pjsip_show_registration",
                {"pbx_id": pbx_id, "registration": registration},
            )

        @self.app.tool(name="asterisk.active_channels")
        def asterisk_active_channels(
            pbx_id: str,
            filter: dict[str, Any] | None = None,
            limit: int = 200,
        ) -> dict[str, Any]:
            """List active channels with optional filters."""
            args: dict[str, Any] = {"pbx_id": pbx_id, "limit": limit}
            if isinstance(filter, dict):
                args["filter"] = filter
            return self._execute("asterisk.active_channels", args)

        @self.app.tool(name="asterisk.bridges")
        def asterisk_bridges(pbx_id: str, limit: int = 200) -> dict[str, Any]:
            """List active bridges."""
            return self._execute("asterisk.bridges", {"pbx_id": pbx_id, "limit": limit})

        @self.app.tool(name="asterisk.channel_details")
        def asterisk_channel_details(pbx_id: str, channel_id: str) -> dict[str, Any]:
            """Get details for a specific channel."""
            return self._execute(
                "asterisk.channel_details",
                {"pbx_id": pbx_id, "channel_id": channel_id},
            )

        @self.app.tool(name="asterisk.reload_pjsip")
        def asterisk_reload_pjsip(pbx_id: str) -> dict[str, Any]:
            """Reload PJSIP module (mode-gated write tool)."""
            return self._execute("asterisk.reload_pjsip", {"pbx_id": pbx_id})

        @self.app.tool(name="freeswitch.health")
        def freeswitch_health(pbx_id: str) -> dict[str, Any]:
            """Check FreeSWITCH ESL health."""
            return self._execute("freeswitch.health", {"pbx_id": pbx_id})

        @self.app.tool(name="freeswitch.sofia_status")
        def freeswitch_sofia_status(
            pbx_id: str,
            profile: str | None = None,
        ) -> dict[str, Any]:
            """Get sofia status with optional profile."""
            args: dict[str, Any] = {"pbx_id": pbx_id}
            if isinstance(profile, str) and profile:
                args["profile"] = profile
            return self._execute("freeswitch.sofia_status", args)

        @self.app.tool(name="freeswitch.registrations")
        def freeswitch_registrations(
            pbx_id: str,
            profile: str | None = None,
            limit: int = 200,
        ) -> dict[str, Any]:
            """List FreeSWITCH registrations."""
            args: dict[str, Any] = {"pbx_id": pbx_id, "limit": limit}
            if isinstance(profile, str) and profile:
                args["profile"] = profile
            return self._execute("freeswitch.registrations", args)

        @self.app.tool(name="freeswitch.gateway_status")
        def freeswitch_gateway_status(pbx_id: str, gateway: str) -> dict[str, Any]:
            """Inspect a FreeSWITCH gateway."""
            return self._execute(
                "freeswitch.gateway_status",
                {"pbx_id": pbx_id, "gateway": gateway},
            )

        @self.app.tool(name="freeswitch.channels")
        def freeswitch_channels(pbx_id: str, limit: int = 200) -> dict[str, Any]:
            """List FreeSWITCH channels."""
            return self._execute("freeswitch.channels", {"pbx_id": pbx_id, "limit": limit})

        @self.app.tool(name="freeswitch.calls")
        def freeswitch_calls(pbx_id: str, limit: int = 200) -> dict[str, Any]:
            """List FreeSWITCH calls."""
            return self._execute("freeswitch.calls", {"pbx_id": pbx_id, "limit": limit})

        @self.app.tool(name="freeswitch.reloadxml")
        def freeswitch_reloadxml(pbx_id: str) -> dict[str, Any]:
            """Reload FreeSWITCH XML config (mode-gated write tool)."""
            return self._execute("freeswitch.reloadxml", {"pbx_id": pbx_id})

        @self.app.tool(name="freeswitch.sofia_profile_rescan")
        def freeswitch_sofia_profile_rescan(pbx_id: str, profile: str) -> dict[str, Any]:
            """Rescan a FreeSWITCH sofia profile (mode-gated write tool)."""
            return self._execute(
                "freeswitch.sofia_profile_rescan",
                {"pbx_id": pbx_id, "profile": profile},
            )

    def _register_resources(self) -> None:
        @self.app.resource("contract://inbound-call/v0.1")
        def contract_inbound_call_v01() -> str:
            path = Path("docs/modernization/state/inbound-call-v0.1.json")
            if not path.exists():
                return json.dumps({"error": "contract file missing"}, indent=2)
            return path.read_text(encoding="utf-8")

        @self.app.resource("audit://mcp-python-sdk-integration/latest")
        def audit_mcp_python_sdk_latest() -> str:
            latest = _latest_audit_file()
            if latest is None:
                return "No mcp-python-sdk-integration audit file found."
            return latest.read_text(encoding="utf-8")

    def _register_prompts(self) -> None:
        @self.app.prompt(name="investigate-target-health")
        def investigate_target_health(pbx_id: str = "pbx-1") -> str:
            return (
                "Goal: inspect telecom target health in read-first mode.\\n"
                "Run: telecom.healthcheck, telecom.list_targets, telecom.summary.\\n"
                f"Candidate target: {pbx_id}.\\n"
                "If summary fails, inspect envelope.error.code and avoid write tools in inspect mode."
            )

    def run(self) -> None:
        import anyio

        transport = self.runtime_flags.transport
        if transport == "stdio":
            preflight_error = self._stdio_preflight_error()
            if preflight_error is not None:
                sys.stderr.write(json.dumps(preflight_error) + "\n")
                sys.stderr.flush()
                return
            anyio.run(self._run_stdio_async)
            return

        run = getattr(self.app, "run", None)
        if run is None:
            raise RuntimeError("MCP SDK server object has no run()")
        try:
            run(transport=transport)
        except TypeError:
            run()

    def _stdio_preflight_error(self) -> dict[str, Any] | None:
        if sys.stdin is None:
            return {
                "level": "error",
                "code": "STDIN_UNAVAILABLE",
                "message": "STDIN is unavailable for MCP stdio transport.",
                "details": {"reason": "stdin is None"},
            }
        if sys.stdin.closed:
            return {
                "level": "error",
                "code": "STDIN_UNAVAILABLE",
                "message": "STDIN is unavailable for MCP stdio transport.",
                "details": {"reason": "stdin is closed"},
            }
        try:
            _ = sys.stdin.fileno()
        except (OSError, ValueError) as exc:
            return {
                "level": "error",
                "code": "STDIN_UNAVAILABLE",
                "message": "STDIN is unavailable for MCP stdio transport.",
                "details": {"error": str(exc)},
            }
        return None

    async def _run_stdio_async(self) -> None:
        import anyio
        import mcp.types as mcp_types
        from mcp.shared.message import SessionMessage

        lowlevel = getattr(self.app, "_mcp_server", None)
        if lowlevel is None:
            raise RuntimeError("FastMCP server missing _mcp_server")

        read_writer, read_stream = anyio.create_memory_object_stream[SessionMessage | Exception](0)
        write_stream, write_reader = anyio.create_memory_object_stream[SessionMessage](0)

        async def stdin_reader() -> None:
            async with read_writer:
                while True:
                    try:
                        raw = await anyio.to_thread.run_sync(sys.stdin.readline)
                    except (PermissionError, OSError, ValueError) as exc:
                        warning = {
                            "level": "warning",
                            "code": "STDIN_UNAVAILABLE",
                            "message": "STDIN became unavailable for MCP stdio transport; exiting cleanly.",
                            "details": {"error": str(exc)},
                        }
                        sys.stderr.write(json.dumps(warning) + "\n")
                        sys.stderr.flush()
                        return
                    if not raw:
                        break
                    try:
                        message = mcp_types.JSONRPCMessage.model_validate_json(raw)
                    except Exception as exc:
                        await read_writer.send(exc)
                        continue
                    await read_writer.send(SessionMessage(message))

        async def stdout_writer() -> None:
            async with write_reader:
                async for session_message in write_reader:
                    payload = session_message.message.model_dump_json(
                        by_alias=True,
                        exclude_none=True,
                    )
                    sys.stdout.write(payload + "\n")
                    sys.stdout.flush()

        async with anyio.create_task_group() as tg:
            tg.start_soon(stdin_reader)
            tg.start_soon(stdout_writer)
            await lowlevel.run(
                read_stream,
                write_stream,
                lowlevel.create_initialization_options(),
            )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="telecom-mcp MCP Python SDK server")
    parser.add_argument(
        "--transport",
        default=None,
        choices=["stdio", "http"],
        help="Override TELECOM_MCP_TRANSPORT for this process",
    )
    parser.add_argument(
        "--targets-file",
        default=None,
        help="Path to targets YAML. Falls back to TELECOM_MCP_TARGETS_FILE or common defaults.",
    )
    parser.add_argument(
        "--mode",
        default="inspect",
        choices=[m.value for m in Mode],
        help="Authorization mode for tool execution wrappers.",
    )
    parser.add_argument(
        "--write-allowlist",
        default="",
        help="Comma-separated list of write tools enabled in execute_safe/execute_full",
    )
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    flags = load_runtime_flags()
    if args.transport:
        flags = RuntimeFlags(
            fixtures=flags.fixtures,
            real_pbx=flags.real_pbx,
            transport=args.transport,
        )

    write_allowlist = [
        item.strip() for item in args.write_allowlist.split(",") if item.strip()
    ]

    try:
        server = TelecomMcpSdkServer(
            runtime_flags=flags,
            targets_file=args.targets_file,
            mode=args.mode,
            write_allowlist=write_allowlist,
        )
        server.run()
        return 0
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", "unknown")
        sys.stderr.write(
            "startup_error code=VALIDATION_ERROR "
            f"message=Missing runtime dependency '{missing}'. "
            "Use the project virtualenv interpreter to run telecom_mcp.mcp_server.\n"
        )
        return 2
