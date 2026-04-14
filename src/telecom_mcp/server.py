"""STDIO MCP-like server dispatch for telecom-mcp."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .authz import Mode, parse_mode, require_mode
from .config import Settings, load_settings
from .envelope import build_envelope
from .errors import (
    AUTH_FAILED,
    NOT_ALLOWED,
    NOT_FOUND,
    TIMEOUT,
    VALIDATION_ERROR,
    ToolError,
    map_exception,
)
from .freeswitch_events import FreeSWITCHEventMonitor, NullFreeSWITCHEventMonitor
from .logging import AuditLogger
from .observability import MetricsRecorder
from .rate_limit import CooldownStore, WindowRateLimiter
from .tools import asterisk, freeswitch, telecom

ToolFunc = Callable[[Any, dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]]
ALL_CAPABILITY_CLASSES = ("observability", "validation", "chaos", "remediation", "export")
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
_LAB_RUNTIME_PROFILES = {"lab", "test", "ci", "dev"}


@dataclass(slots=True)
class CallerContext:
    principal: str
    authenticated: bool
    auth_scheme: str


@dataclass(slots=True)
class ServerContext:
    settings: Settings
    mode: Mode
    audit: AuditLogger
    metrics: MetricsRecorder
    server: "TelecomMCPServer"
    deadline_monotonic: float
    correlation_id: str
    current_tool_name: str
    caller: CallerContext | None = None

    def call_tool_internal(
        self, tool_name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        self.raise_if_deadline_exceeded(operation=tool_name)
        return self.server.execute_tool(
            tool_name=tool_name,
            args=args,
            correlation_id=f"c-internal-{uuid.uuid4().hex[:8]}",
            deadline_monotonic=self.deadline_monotonic,
            caller=self.caller,
        )

    def remaining_timeout_s(self, fallback_s: float = 4.0) -> float:
        remaining = self.deadline_monotonic - time.monotonic()
        if remaining <= 0:
            return 0.001
        return max(0.001, min(fallback_s, remaining))

    def raise_if_deadline_exceeded(self, operation: str) -> None:
        remaining = self.deadline_monotonic - time.monotonic()
        if remaining <= 0:
            raise ToolError(
                TIMEOUT,
                f"Tool deadline exceeded before operation: {operation}",
                {
                    "operation": operation,
                    "timeout_seconds": self.settings.tool_timeout_seconds,
                },
            )


class TelecomMCPServer:
    def __init__(
        self,
        settings: Settings,
        *,
        mode: Mode | None = None,
        audit: AuditLogger | None = None,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self.settings = settings
        self.mode = mode or settings.mode
        self.audit = audit or AuditLogger()
        self.metrics = metrics or MetricsRecorder()
        self.cooldown_store = CooldownStore()
        self.rate_limiter = WindowRateLimiter()
        self._freeswitch_event_monitors: dict[str, FreeSWITCHEventMonitor] = {}
        self._freeswitch_event_monitor_lock = threading.Lock()
        self.tool_registry: dict[str, tuple[ToolFunc, Mode]] = {
            "telecom.list_targets": (telecom.list_targets, Mode.INSPECT),
            "telecom.summary": (telecom.summary, Mode.INSPECT),
            "telecom.capture_snapshot": (telecom.capture_snapshot, Mode.INSPECT),
            "telecom.endpoints": (telecom.endpoints, Mode.INSPECT),
            "telecom.registrations": (telecom.registrations, Mode.INSPECT),
            "telecom.channels": (telecom.channels, Mode.INSPECT),
            "telecom.calls": (telecom.calls, Mode.INSPECT),
            "telecom.logs": (telecom.logs, Mode.INSPECT),
            "telecom.inventory": (telecom.inventory, Mode.INSPECT),
            "telecom.diff_snapshots": (telecom.diff_snapshots, Mode.INSPECT),
            "telecom.compare_targets": (telecom.compare_targets, Mode.INSPECT),
            "telecom.run_smoke_test": (telecom.run_smoke_test, Mode.INSPECT),
            "telecom.run_playbook": (telecom.run_playbook, Mode.INSPECT),
            "telecom.run_smoke_suite": (telecom.run_smoke_suite, Mode.INSPECT),
            "telecom.baseline_create": (telecom.baseline_create, Mode.INSPECT),
            "telecom.baseline_show": (telecom.baseline_show, Mode.INSPECT),
            "telecom.audit_target": (telecom.audit_target, Mode.INSPECT),
            "telecom.drift_target_vs_baseline": (
                telecom.drift_target_vs_baseline,
                Mode.INSPECT,
            ),
            "telecom.drift_compare_targets": (
                telecom.drift_compare_targets,
                Mode.INSPECT,
            ),
            "telecom.audit_report": (telecom.audit_report, Mode.INSPECT),
            "telecom.audit_export": (telecom.audit_export, Mode.INSPECT),
            "telecom.scorecard_target": (telecom.scorecard_target, Mode.INSPECT),
            "telecom.scorecard_cluster": (telecom.scorecard_cluster, Mode.INSPECT),
            "telecom.scorecard_environment": (
                telecom.scorecard_environment,
                Mode.INSPECT,
            ),
            "telecom.scorecard_compare": (telecom.scorecard_compare, Mode.INSPECT),
            "telecom.scorecard_trend": (telecom.scorecard_trend, Mode.INSPECT),
            "telecom.scorecard_export": (telecom.scorecard_export, Mode.INSPECT),
            "telecom.scorecard_policy_inputs": (
                telecom.scorecard_policy_inputs,
                Mode.INSPECT,
            ),
            "telecom.capture_incident_evidence": (
                telecom.capture_incident_evidence,
                Mode.INSPECT,
            ),
            "telecom.generate_evidence_pack": (
                telecom.generate_evidence_pack,
                Mode.INSPECT,
            ),
            "telecom.reconstruct_incident_timeline": (
                telecom.reconstruct_incident_timeline,
                Mode.INSPECT,
            ),
            "telecom.export_evidence_pack": (
                telecom.export_evidence_pack,
                Mode.INSPECT,
            ),
            "telecom.list_probes": (telecom.list_probes, Mode.INSPECT),
            "telecom.run_probe": (telecom.run_probe, Mode.INSPECT),
            "telecom.list_chaos_scenarios": (
                telecom.list_chaos_scenarios,
                Mode.INSPECT,
            ),
            "telecom.run_chaos_scenario": (
                telecom.run_chaos_scenario,
                Mode.INSPECT,
            ),
            "telecom.list_self_healing_policies": (
                telecom.list_self_healing_policies,
                Mode.INSPECT,
            ),
            "telecom.evaluate_self_healing": (
                telecom.evaluate_self_healing,
                Mode.INSPECT,
            ),
            "telecom.run_self_healing_policy": (
                telecom.run_self_healing_policy,
                Mode.INSPECT,
            ),
            "telecom.release_gate_decision": (
                telecom.release_gate_decision,
                Mode.INSPECT,
            ),
            "telecom.release_promotion_decision": (
                telecom.release_promotion_decision,
                Mode.INSPECT,
            ),
            "telecom.release_gate_history": (
                telecom.release_gate_history,
                Mode.INSPECT,
            ),
            "telecom.assert_state": (telecom.assert_state, Mode.INSPECT),
            "telecom.run_registration_probe": (
                telecom.run_registration_probe,
                Mode.EXECUTE_SAFE,
            ),
            "telecom.run_trunk_probe": (telecom.run_trunk_probe, Mode.EXECUTE_SAFE),
            "telecom.verify_cleanup": (telecom.verify_cleanup, Mode.INSPECT),
            "asterisk.health": (asterisk.health, Mode.INSPECT),
            "asterisk.pjsip_show_endpoint": (
                asterisk.pjsip_show_endpoint,
                Mode.INSPECT,
            ),
            "asterisk.pjsip_show_endpoints": (
                asterisk.pjsip_show_endpoints,
                Mode.INSPECT,
            ),
            "asterisk.pjsip_show_registration": (
                asterisk.pjsip_show_registration,
                Mode.INSPECT,
            ),
            "asterisk.pjsip_show_contacts": (
                asterisk.pjsip_show_contacts,
                Mode.INSPECT,
            ),
            "asterisk.active_channels": (asterisk.active_channels, Mode.INSPECT),
            "asterisk.bridges": (asterisk.bridges, Mode.INSPECT),
            "asterisk.channel_details": (asterisk.channel_details, Mode.INSPECT),
            "asterisk.core_show_channel": (asterisk.core_show_channel, Mode.INSPECT),
            "asterisk.version": (asterisk.version, Mode.INSPECT),
            "asterisk.modules": (asterisk.modules, Mode.INSPECT),
            "asterisk.logs": (asterisk.logs, Mode.INSPECT),
            "asterisk.cli": (asterisk.cli, Mode.INSPECT),
            "asterisk.originate_probe": (asterisk.originate_probe, Mode.EXECUTE_SAFE),
            "asterisk.reload_pjsip": (asterisk.reload_pjsip, Mode.EXECUTE_SAFE),
            "freeswitch.health": (freeswitch.health, Mode.INSPECT),
            "freeswitch.capabilities": (freeswitch.capabilities, Mode.INSPECT),
            "freeswitch.recent_events": (freeswitch.recent_events, Mode.INSPECT),
            "freeswitch.sofia_status": (freeswitch.sofia_status, Mode.INSPECT),
            "freeswitch.registrations": (freeswitch.registrations, Mode.INSPECT),
            "freeswitch.gateway_status": (freeswitch.gateway_status, Mode.INSPECT),
            "freeswitch.channels": (freeswitch.channels, Mode.INSPECT),
            "freeswitch.calls": (freeswitch.calls, Mode.INSPECT),
            "freeswitch.channel_details": (freeswitch.channel_details, Mode.INSPECT),
            "freeswitch.version": (freeswitch.version, Mode.INSPECT),
            "freeswitch.modules": (freeswitch.modules, Mode.INSPECT),
            "freeswitch.logs": (freeswitch.logs, Mode.INSPECT),
            "freeswitch.api": (freeswitch.api, Mode.INSPECT),
            "freeswitch.originate_probe": (
                freeswitch.originate_probe,
                Mode.EXECUTE_SAFE,
            ),
            "freeswitch.reloadxml": (freeswitch.reloadxml, Mode.EXECUTE_SAFE),
            "freeswitch.sofia_profile_rescan": (
                freeswitch.sofia_profile_rescan,
                Mode.EXECUTE_SAFE,
            ),
        }
        self.tool_capability_class = self._build_tool_capability_classes()
        self.allowed_capability_classes = self._resolve_allowed_capability_classes()

    def get_freeswitch_event_monitor(self, pbx_id: str) -> FreeSWITCHEventMonitor | NullFreeSWITCHEventMonitor:
        target = self.settings.get_target(pbx_id)
        if target.type != "freeswitch" or target.esl is None:
            return NullFreeSWITCHEventMonitor()
        with self._freeswitch_event_monitor_lock:
            monitor = self._freeswitch_event_monitors.get(pbx_id)
            if monitor is None:
                monitor = FreeSWITCHEventMonitor(
                    pbx_id=pbx_id,
                    config=target.esl,
                    connector_factory=freeswitch.FreeSWITCHESLConnector,
                )
                self._freeswitch_event_monitors[pbx_id] = monitor
        return monitor

    def _build_tool_capability_classes(self) -> dict[str, str]:
        classes = {name: "observability" for name in self.tool_registry}
        for name in (
            "telecom.run_smoke_test",
            "telecom.run_playbook",
            "telecom.run_smoke_suite",
            "telecom.list_probes",
            "telecom.run_probe",
            "telecom.assert_state",
            "telecom.run_registration_probe",
            "telecom.run_trunk_probe",
            "telecom.verify_cleanup",
            "telecom.release_gate_decision",
        ):
            if name in classes:
                classes[name] = "validation"
        for name in ("telecom.list_chaos_scenarios", "telecom.run_chaos_scenario"):
            if name in classes:
                classes[name] = "chaos"
        for name in (
            "telecom.list_self_healing_policies",
            "telecom.evaluate_self_healing",
            "telecom.run_self_healing_policy",
            "asterisk.reload_pjsip",
            "freeswitch.reloadxml",
            "freeswitch.sofia_profile_rescan",
        ):
            if name in classes:
                classes[name] = "remediation"
        for name in (
            "telecom.audit_export",
            "telecom.scorecard_export",
            "telecom.export_evidence_pack",
        ):
            if name in classes:
                classes[name] = "export"
        return classes

    def _resolve_allowed_capability_classes(self) -> set[str]:
        configured = os.getenv("TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES", "").strip()
        if not configured:
            profile = os.getenv("TELECOM_MCP_RUNTIME_PROFILE", "").strip().lower()
            if profile in _LAB_RUNTIME_PROFILES:
                return set(ALL_CAPABILITY_CLASSES)
            return {"observability"}
        parsed = {
            item.strip().lower() for item in configured.split(",") if item.strip()
        }
        allowed = parsed.intersection(ALL_CAPABILITY_CLASSES)
        return allowed or {"observability"}

    def _enforce_capability_class_policy(
        self, tool_name: str, capability_class: str
    ) -> None:
        if capability_class not in ALL_CAPABILITY_CLASSES:
            raise ToolError(
                NOT_ALLOWED,
                "Tool capability class is not recognized by policy",
                {"tool": tool_name, "capability_class": capability_class},
            )
        if capability_class not in self.allowed_capability_classes:
            raise ToolError(
                NOT_ALLOWED,
                "Tool capability class is not allowed by runtime policy",
                {
                    "tool": tool_name,
                    "capability_class": capability_class,
                    "allowed_capability_classes": sorted(
                        self.allowed_capability_classes
                    ),
                    "policy_env": "TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES",
                },
            )

    def _enforce_write_policy(self, tool_name: str, pbx_id: str | None) -> None:
        if tool_name not in self.settings.write_allowlist:
            raise ToolError(
                NOT_ALLOWED,
                f"Write tool not allowlisted: {tool_name}",
                {"tool": tool_name},
            )
        key = f"{tool_name}:{pbx_id or 'global'}"
        if not self.cooldown_store.allowed(key, self.settings.cooldown_seconds):
            raise ToolError(
                NOT_ALLOWED,
                f"Write tool cooldown active for {tool_name}",
                {"tool": tool_name, "cooldown_seconds": self.settings.cooldown_seconds},
            )

    def _enforce_write_intent(
        self, tool_name: str, args: dict[str, Any], pbx_id: str | None
    ) -> None:
        reason = args.get("reason")
        change_ticket = args.get("change_ticket")
        if isinstance(reason, str):
            reason = reason.strip()
        if isinstance(change_ticket, str):
            change_ticket = change_ticket.strip()
        if not reason or not change_ticket:
            raise ToolError(
                VALIDATION_ERROR,
                "Write tools require non-empty 'reason' and 'change_ticket' fields",
                {
                    "tool": tool_name,
                    "pbx_id": pbx_id,
                    "required_fields": ["reason", "change_ticket"],
                },
            )
        expected_token = os.getenv("TELECOM_MCP_CONFIRM_TOKEN", "").strip()
        require_confirm_token = (
            os.getenv("TELECOM_MCP_REQUIRE_CONFIRM_TOKEN", "").strip() == "1"
        )
        if require_confirm_token and not expected_token:
            raise ToolError(
                NOT_ALLOWED,
                "Write tool confirmation token policy enabled but token is not configured",
                {
                    "tool": tool_name,
                    "pbx_id": pbx_id,
                    "required_env": "TELECOM_MCP_CONFIRM_TOKEN",
                    "policy_env": "TELECOM_MCP_REQUIRE_CONFIRM_TOKEN",
                },
            )
        if expected_token or require_confirm_token:
            supplied = args.get("confirm_token")
            supplied_token = supplied.strip() if isinstance(supplied, str) else ""
            if supplied_token != expected_token:
                raise ToolError(
                    NOT_ALLOWED,
                    "Write tool confirmation token missing or invalid",
                    {
                        "tool": tool_name,
                        "pbx_id": pbx_id,
                        "required_field": "confirm_token",
                        "token_source_env": "TELECOM_MCP_CONFIRM_TOKEN",
                    },
                )

    def _enforce_rate_limit(self, tool_name: str, pbx_id: str | None) -> None:
        scope = pbx_id or "global"
        key = f"{tool_name}:{scope}"
        allowed, current = self.rate_limiter.allow(
            key,
            max_calls=self.settings.max_calls_per_window,
            window_seconds=self.settings.rate_limit_window_seconds,
        )
        if not allowed:
            self.metrics.increment_tool_rate_limited(tool_name, scope)
            raise ToolError(
                NOT_ALLOWED,
                f"Rate limit exceeded for {tool_name}",
                {
                    "tool": tool_name,
                    "scope": scope,
                    "max_calls_per_window": self.settings.max_calls_per_window,
                    "rate_limit_window_seconds": self.settings.rate_limit_window_seconds,
                    "current_window_calls": current,
                },
            )

    def execute_tool(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        correlation_id: str | None = None,
        deadline_monotonic: float | None = None,
        caller: CallerContext | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        correlation_id = correlation_id or f"c-{uuid.uuid4().hex[:12]}"
        if deadline_monotonic is None:
            deadline_monotonic = started + self.settings.tool_timeout_seconds
        pbx_id = args.get("pbx_id") if isinstance(args, dict) else None
        target = {"type": "telecom", "id": pbx_id or "unknown"}
        if isinstance(pbx_id, str) and pbx_id:
            try:
                resolved_target = self.settings.get_target(pbx_id)
                target = {"type": resolved_target.type, "id": resolved_target.id}
            except ToolError:
                target = {"type": "telecom", "id": pbx_id}

        try:
            if tool_name not in self.tool_registry:
                raise ToolError(NOT_FOUND, f"Unknown tool: {tool_name}")

            tool_fn, minimum_mode = self.tool_registry[tool_name]
            capability_class = self.tool_capability_class.get(tool_name, "observability")
            self._enforce_capability_class_policy(tool_name, capability_class)
            require_mode(tool_name, self.mode, minimum_mode)
            self._enforce_rate_limit(tool_name, pbx_id)
            if minimum_mode in {Mode.EXECUTE_SAFE, Mode.EXECUTE_FULL}:
                self._enforce_write_policy(tool_name, pbx_id)
                self._enforce_write_intent(tool_name, args, pbx_id)
            ctx = ServerContext(
                settings=self.settings,
                mode=self.mode,
                audit=self.audit,
                metrics=self.metrics,
                server=self,
                deadline_monotonic=deadline_monotonic,
                correlation_id=correlation_id,
                current_tool_name=tool_name,
                caller=caller,
            )
            target, data = tool_fn(ctx, args)
            if time.monotonic() > deadline_monotonic:
                raise ToolError(
                    TIMEOUT,
                    f"Tool execution timed out: {tool_name}",
                    {
                        "tool": tool_name,
                        "timeout_seconds": self.settings.tool_timeout_seconds,
                    },
                )
            duration_ms = int((time.monotonic() - started) * 1000)
            self.metrics.record_tool_latency(tool_name, duration_ms)
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
                principal=(caller.principal if caller else None),
                principal_authenticated=(caller.authenticated if caller else False),
                auth_scheme=(caller.auth_scheme if caller else None),
            )
            return envelope
        except Exception as exc:
            err = map_exception(exc)
            duration_ms = int((time.monotonic() - started) * 1000)
            self.metrics.record_tool_latency(tool_name, duration_ms)
            self.metrics.increment_tool_error(tool_name, err.code)
            if err.code == TIMEOUT and not err.details:
                err.details = {"tool": tool_name}
            if err.code == TIMEOUT:
                timeout_details = dict(err.details or {})
                timeout_details.setdefault(
                    "timeout_seconds", self.settings.tool_timeout_seconds
                )
                timeout_details["duration_ms"] = duration_ms
                err.details = timeout_details
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
                principal=(caller.principal if caller else None),
                principal_authenticated=(caller.authenticated if caller else False),
                auth_scheme=(caller.auth_scheme if caller else None),
            )
            return envelope

    def _resolve_caller(self, payload: dict[str, Any]) -> CallerContext | None:
        caller_raw = payload.get("caller")
        caller = caller_raw.strip() if isinstance(caller_raw, str) else ""
        auth_payload = payload.get("auth")
        token = ""
        if isinstance(auth_payload, dict):
            token_raw = auth_payload.get("token")
            token = token_raw.strip() if isinstance(token_raw, str) else ""

        require_auth_raw = (
            os.getenv("TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER", "")
            .strip()
            .lower()
        )
        runtime_profile = os.getenv("TELECOM_MCP_RUNTIME_PROFILE", "").strip().lower()
        if require_auth_raw:
            require_auth = require_auth_raw in _TRUTHY_ENV_VALUES
        else:
            require_auth = runtime_profile not in _LAB_RUNTIME_PROFILES
        expected_token = os.getenv("TELECOM_MCP_AUTH_TOKEN", "").strip()
        allowed_callers_raw = os.getenv("TELECOM_MCP_ALLOWED_CALLERS", "").strip()
        allowed_callers = {
            item.strip()
            for item in allowed_callers_raw.split(",")
            if item.strip()
        }

        authenticated = False
        auth_scheme = "none"
        if caller == "mcp-sdk":
            return CallerContext(
                principal=caller,
                authenticated=True,
                auth_scheme="internal",
            )
        if expected_token:
            auth_scheme = "shared_token"
            authenticated = token == expected_token and bool(caller)

        if require_auth and not caller:
            raise ToolError(
                AUTH_FAILED,
                "Authenticated caller identity is required",
                {"required_field": "caller"},
            )
        if require_auth and expected_token and not authenticated:
            raise ToolError(
                AUTH_FAILED,
                "Caller authentication failed",
                {
                    "required_field": "auth.token",
                    "token_source_env": "TELECOM_MCP_AUTH_TOKEN",
                },
            )
        if require_auth and not expected_token:
            raise ToolError(
                AUTH_FAILED,
                "Authenticated caller policy enabled but TELECOM_MCP_AUTH_TOKEN is unset",
                {"required_env": "TELECOM_MCP_AUTH_TOKEN"},
            )
        if caller and allowed_callers and caller not in allowed_callers:
            raise ToolError(
                AUTH_FAILED,
                "Caller is not authorized for this runtime",
                {"caller": caller, "allowed_callers": sorted(allowed_callers)},
            )
        if not caller:
            return None
        return CallerContext(
            principal=caller,
            authenticated=authenticated,
            auth_scheme=auth_scheme,
        )

    def handle_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        tool_name = payload.get("tool")
        args = payload.get("args", {})
        correlation_id = payload.get("correlation_id")

        if not isinstance(tool_name, str):
            raise ToolError(VALIDATION_ERROR, "Request missing 'tool' string")
        if not isinstance(args, dict):
            raise ToolError(VALIDATION_ERROR, "Request 'args' must be an object")

        caller = self._resolve_caller(payload)
        return self.execute_tool(
            tool_name=tool_name,
            args=args,
            correlation_id=correlation_id,
            caller=caller,
        )

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
    parser.add_argument(
        "--write-allowlist",
        default="",
        help="Comma-separated list of write tools enabled in execute_safe/execute_full",
    )
    parser.add_argument("--cooldown-seconds", type=int, default=30)
    parser.add_argument("--max-calls-per-window", type=int, default=200)
    parser.add_argument("--rate-limit-window-seconds", type=float, default=1.0)
    parser.add_argument("--tool-timeout-seconds", type=float, default=5.0)
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        write_allowlist = [
            item.strip() for item in args.write_allowlist.split(",") if item.strip()
        ]
        settings = load_settings(
            args.targets_file,
            mode=args.mode,
            write_allowlist=write_allowlist,
            cooldown_seconds=args.cooldown_seconds,
            max_calls_per_window=args.max_calls_per_window,
            rate_limit_window_seconds=args.rate_limit_window_seconds,
            tool_timeout_seconds=args.tool_timeout_seconds,
        )
        server = TelecomMCPServer(settings=settings, mode=parse_mode(args.mode))
        server.run_stdio()
        return 0
    except ToolError as exc:
        sys.stderr.write(f"startup_error code={exc.code} message={exc.message}\n")
        return 2
