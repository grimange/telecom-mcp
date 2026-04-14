"""MCP Python SDK server integration for telecom-mcp."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import sys
import time
import uuid
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from telecom_mcp.authz import Mode, parse_mode
from telecom_mcp.config import Settings, load_settings
from telecom_mcp.envelope import build_envelope
from telecom_mcp.errors import AUTH_FAILED, VALIDATION_ERROR, ToolError
from telecom_mcp.mcp_server.runtime import RuntimeFlags, iso8601_now, load_runtime_flags
from telecom_mcp.server import TelecomMCPServer


class SnapshotInclude(TypedDict, total=False):
    endpoints: bool
    trunks: bool
    calls: bool
    registrations: bool


class SnapshotLimits(TypedDict, total=False):
    max_items: int


class EndpointFilter(TypedDict, total=False):
    starts_with: str
    contains: str


class ActiveChannelFilter(TypedDict):
    state: NotRequired[str]
    caller: NotRequired[str]
    callee: NotRequired[str]


class LogFilter(TypedDict, total=False):
    grep: str
    tail: int
    level: str


class SnapshotPayload(TypedDict, total=False):
    snapshot_id: str
    captured_at: str
    summary: dict[str, Any]
    endpoints: list[dict[str, Any]]
    trunks: list[dict[str, Any]]
    calls: list[dict[str, Any]]


class AssertionParams(TypedDict, total=False):
    value: int | str | bool


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


def _require_authenticated_caller_effective() -> bool:
    raw = os.getenv("TELECOM_MCP_REQUIRE_AUTHENTICATED_CALLER", "").strip().lower()
    if raw:
        return raw in {"1", "true", "yes", "on"}
    profile = os.getenv("TELECOM_MCP_RUNTIME_PROFILE", "").strip().lower()
    return profile not in {"lab", "test", "ci", "dev"}


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


def _targets_file_source(
    *,
    explicit: str | None,
    env_path: str | None,
    resolved: Path,
) -> str:
    if explicit:
        explicit_path = Path(explicit).expanduser().resolve()
        if explicit_path == resolved:
            return "cli_arg"
    if env_path:
        env_resolved = Path(env_path).expanduser().resolve()
        if env_resolved == resolved:
            return "env"
    return "fallback_default"


def _coerce_positive_int(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.isdigit():
            return int(candidate)
    return value


def _coerce_object_arg(value: Any) -> Any:
    if isinstance(value, dict) or value is None:
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return value
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return value
        if isinstance(parsed, dict):
            return parsed
    return value


def _coerce_include_arg(value: Any) -> Any:
    if isinstance(value, dict) or value is None:
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return value
        parsed = _coerce_object_arg(candidate)
        if isinstance(parsed, dict):
            return parsed
        allowed = {"endpoints", "trunks", "calls", "registrations"}
        tokens = [token.strip() for token in candidate.split(",") if token.strip()]
        if tokens and all(token in allowed for token in tokens):
            return {token: True for token in tokens}
    return value


def _coerce_limits_arg(value: Any) -> Any:
    if isinstance(value, dict) or value is None:
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return value
        parsed = _coerce_object_arg(candidate)
        if isinstance(parsed, dict):
            return parsed
        if "=" in candidate:
            key, raw = candidate.split("=", 1)
            if key.strip() == "max_items" and raw.strip().isdigit():
                return {"max_items": int(raw.strip())}
    return value


def _iter_registered_tools(app: Any) -> list[tuple[str, Any]]:
    tools_attr = getattr(app, "tools", None)
    if isinstance(tools_attr, dict):
        return sorted(tools_attr.items(), key=lambda item: item[0])
    manager = getattr(app, "_tool_manager", None)
    if manager is not None:
        manager_tools = getattr(manager, "_tools", None)
        if isinstance(manager_tools, dict):
            return sorted(manager_tools.items(), key=lambda item: item[0])
    return []


class TelecomMcpSdkServer:
    def __init__(
        self,
        *,
        runtime_flags: RuntimeFlags | None = None,
        targets_file: str | None = None,
        mode: str = "inspect",
        write_allowlist: list[str] | None = None,
        cooldown_seconds: int = 30,
        max_calls_per_window: int = 200,
        rate_limit_window_seconds: float = 1.0,
        tool_timeout_seconds: float = 5.0,
        strict_startup: bool | None = None,
    ) -> None:
        self.runtime_flags = runtime_flags or load_runtime_flags()
        self.strict_startup = (
            self.runtime_flags.strict_startup
            if strict_startup is None
            else strict_startup
        )
        self.started_at = iso8601_now()
        self.startup_warnings: list[dict[str, Any]] = []
        self.effective_targets_file: str | None = None
        self.targets_file_source: str | None = None

        self.mode = parse_mode(mode)
        self.settings = self._build_settings(
            targets_file=targets_file,
            mode=self.mode,
            write_allowlist=write_allowlist or [],
            cooldown_seconds=cooldown_seconds,
            max_calls_per_window=max_calls_per_window,
            rate_limit_window_seconds=rate_limit_window_seconds,
            tool_timeout_seconds=tool_timeout_seconds,
        )
        self.core_server = TelecomMCPServer(settings=self.settings, mode=self.mode)

        mcp_class = _import_mcp_server_class()
        self.app = mcp_class("telecom-mcp")
        self._register_tools()
        self._register_resources()
        self._register_prompts()

    def _build_settings(
        self,
        *,
        targets_file: str | None,
        mode: Mode,
        write_allowlist: list[str],
        cooldown_seconds: int,
        max_calls_per_window: int,
        rate_limit_window_seconds: float,
        tool_timeout_seconds: float,
    ) -> Settings:
        self._append_targets_file_hygiene_warnings()
        self._enforce_strict_startup(
            codes={"TARGETS_FILE_DUPLICATE"},
            message="Strict startup rejected duplicate repository targets files.",
        )
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
            self._enforce_strict_startup(
                codes={"TARGETS_FILE_NOT_FOUND"},
                message="Strict startup requires a resolvable targets file.",
            )
            return Settings(
                targets=[],
                mode=mode,
                write_allowlist=write_allowlist,
                cooldown_seconds=cooldown_seconds,
                max_calls_per_window=max_calls_per_window,
                rate_limit_window_seconds=rate_limit_window_seconds,
                tool_timeout_seconds=tool_timeout_seconds,
            )
        self.effective_targets_file = str(resolved_targets)
        self._append_targets_source_warning(resolved_targets)
        env_targets = os.getenv("TELECOM_MCP_TARGETS_FILE", "").strip() or None
        self.targets_file_source = _targets_file_source(
            explicit=targets_file,
            env_path=env_targets,
            resolved=resolved_targets,
        )
        if (
            self.runtime_flags.require_explicit_targets_file
            and self.targets_file_source == "fallback_default"
        ):
            self.startup_warnings.append(
                {
                    "code": "TARGETS_FILE_SOURCE_IMPLICIT",
                    "message": (
                        "Explicit targets file is required by policy; fallback path "
                        "resolution is not permitted."
                    ),
                    "details": {
                        "effective_targets_file": self.effective_targets_file,
                        "required_source": ["cli_arg", "env"],
                        "actual_source": self.targets_file_source,
                    },
                }
            )
        self._enforce_strict_startup(
            codes={"TARGETS_FILE_SOURCE_IMPLICIT"},
            message="Strict startup rejected implicit targets file source.",
        )
        try:
            settings = load_settings(
                resolved_targets,
                mode=mode.value,
                write_allowlist=write_allowlist,
                cooldown_seconds=cooldown_seconds,
                max_calls_per_window=max_calls_per_window,
                rate_limit_window_seconds=rate_limit_window_seconds,
                tool_timeout_seconds=tool_timeout_seconds,
            )
            self._append_runtime_prerequisite_warnings(settings)
            self._enforce_strict_startup(
                codes={"TARGET_PLATFORM_COVERAGE_GAP", "TARGET_SECRETS_MISSING"},
                message=(
                    "Strict startup rejected incomplete platform coverage or "
                    "missing credential environment variables."
                ),
            )
            return settings
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
            self._enforce_strict_startup(
                codes={VALIDATION_ERROR, AUTH_FAILED},
                message="Strict startup rejected invalid or incomplete target configuration.",
            )
            return Settings(
                targets=[],
                mode=mode,
                write_allowlist=write_allowlist,
                cooldown_seconds=cooldown_seconds,
                max_calls_per_window=max_calls_per_window,
                rate_limit_window_seconds=rate_limit_window_seconds,
                tool_timeout_seconds=tool_timeout_seconds,
            )

    def _enforce_strict_startup(self, *, codes: set[str], message: str) -> None:
        if not self.strict_startup:
            return
        matched = [w for w in self.startup_warnings if str(w.get("code")) in codes]
        if not matched:
            return
        raise ToolError(
            VALIDATION_ERROR,
            message,
            {
                "strict_startup": True,
                "blocking_warnings": matched,
            },
        )

    def _append_runtime_prerequisite_warnings(self, settings: Settings) -> None:
        class_policy_raw = os.getenv("TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES", "").strip()
        if (
            settings.mode in {Mode.EXECUTE_SAFE, Mode.EXECUTE_FULL}
            and not class_policy_raw
        ):
            self.startup_warnings.append(
                {
                    "code": "CAPABILITY_CLASS_POLICY_UNSET",
                    "message": (
                        "Write-capable mode is enabled without explicit capability class "
                        "policy; configure TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES."
                    ),
                    "details": {
                        "mode": settings.mode.value,
                        "policy_env": "TELECOM_MCP_ALLOWED_CAPABILITY_CLASSES",
                    },
                }
            )
        if self.runtime_flags.fixtures and not self.runtime_flags.real_pbx:
            self.startup_warnings.append(
                {
                    "code": "FIXTURE_MODE_LIVE_CONNECTORS",
                    "message": (
                        "Fixture mode is enabled, but core telecom tools still use live "
                        "connectors unless tests inject mocks."
                    ),
                    "details": {
                        "fixtures": self.runtime_flags.fixtures,
                        "real_backend": self.runtime_flags.real_pbx,
                    },
                }
            )
        self.startup_warnings.append(
            {
                "code": "BACKEND_NETWORK_REQUIRED",
                "message": (
                    "Backend-dependent tools require PBX network reachability and "
                    "configured secret environment variables."
                ),
                "details": {"targets": len(settings.targets)},
            }
        )
        platform_types = {target.type for target in settings.targets}
        missing_platforms = sorted(
            {"asterisk", "freeswitch"} - platform_types
        )
        if missing_platforms:
            self.startup_warnings.append(
                {
                    "code": "TARGET_PLATFORM_COVERAGE_GAP",
                    "message": (
                        "Some tool families are exported without corresponding target types "
                        "in the configured catalog."
                    ),
                    "details": {
                        "configured_platforms": sorted(platform_types),
                        "missing_platforms": missing_platforms,
                        "targets_count": len(settings.targets),
                    },
                }
            )
        for target in settings.targets:
            missing_env: list[str] = []
            if target.ami:
                for env_name in [target.ami.username_env, target.ami.password_env]:
                    if env_name and not os.getenv(env_name):
                        missing_env.append(env_name)
            if target.ari:
                for env_name in [target.ari.username_env, target.ari.password_env]:
                    if env_name and not os.getenv(env_name):
                        missing_env.append(env_name)
            if target.esl:
                env_name = target.esl.password_env
                if env_name and not os.getenv(env_name):
                    missing_env.append(env_name)
            if missing_env:
                self.startup_warnings.append(
                    {
                        "code": "TARGET_SECRETS_MISSING",
                        "message": (
                            "One or more required credential environment variables are missing "
                            "for this target."
                        ),
                        "details": {
                            "pbx_id": target.id,
                            "target_type": target.type,
                            "missing_env": sorted(set(missing_env)),
                        },
                    }
                )
            if target.type == "asterisk" and target.ami:
                self.startup_warnings.append(
                    {
                        "code": "AMI_PJSIP_PERMISSIONS_UNVERIFIED",
                        "message": (
                            "AMI credentials are configured, but PJSIP action permissions "
                            "must be verified to avoid NOT_ALLOWED failures."
                        ),
                        "details": {"pbx_id": target.id},
                    }
                )

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

    def _append_targets_source_warning(self, resolved_targets: Path) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        canonical = repo_root / "targets.yaml"
        if not canonical.exists():
            return
        if resolved_targets == canonical:
            return
        self.startup_warnings.append(
            {
                "code": "TARGETS_FILE_NON_CANONICAL",
                "message": (
                    "Runtime targets file differs from repository canonical targets.yaml; "
                    "verify you are editing and launching the same file."
                ),
                "details": {
                    "effective_targets_file": str(resolved_targets),
                    "canonical_targets_file": str(canonical),
                },
            }
        )

    def _execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        caller = os.getenv("TELECOM_MCP_CALLER_ID", "").strip() or "mcp-sdk"
        payload: dict[str, Any] = {"caller": caller}
        token = os.getenv("TELECOM_MCP_CALLER_TOKEN", "").strip()
        if token:
            payload["auth"] = {"token": token}
        caller_ctx = self.core_server._resolve_caller(payload)
        return self.core_server.execute_tool(
            tool_name=tool_name,
            args=args,
            caller=caller_ctx,
        )

    def _runtime_build_info(self) -> dict[str, Any]:
        module_path = Path(__file__).resolve()
        module_mtime = int(module_path.stat().st_mtime) if module_path.exists() else None
        try:
            package_version = importlib_metadata.version("telecom-mcp")
        except importlib_metadata.PackageNotFoundError:
            package_version = "unknown"
        contract_items: list[str] = []
        registered_tools = _iter_registered_tools(self.app)
        for tool_name, tool_obj in registered_tools:
            fn = getattr(tool_obj, "fn", None) if tool_obj is not None else None
            if fn is None:
                fn = tool_obj
            try:
                sig = inspect.signature(fn)
            except (TypeError, ValueError):
                sig = "(unknown)"
            contract_items.append(f"{tool_name}:{sig}")
        contract_fingerprint = hashlib.sha256(
            "\n".join(contract_items).encode("utf-8")
        ).hexdigest()[:16]
        return {
            "package_version": package_version,
            "module_path": str(module_path),
            "module_mtime_epoch": module_mtime,
            "tool_count": len(registered_tools),
            "tool_contract_fingerprint": contract_fingerprint,
        }

    def _healthcheck_envelope(self) -> dict[str, Any]:
        started = time.monotonic()
        correlation_id = f"c-health-{uuid.uuid4().hex[:10]}"
        target_capabilities: list[dict[str, Any]] = []
        for target in self.settings.targets:
            missing_env: list[str] = []
            if target.ami:
                for env_name in [target.ami.username_env, target.ami.password_env]:
                    if env_name and not os.getenv(env_name):
                        missing_env.append(env_name)
            if target.ari:
                for env_name in [target.ari.username_env, target.ari.password_env]:
                    if env_name and not os.getenv(env_name):
                        missing_env.append(env_name)
            if target.esl:
                env_name = target.esl.password_env
                if env_name and not os.getenv(env_name):
                    missing_env.append(env_name)
            target_capabilities.append(
                {
                    "pbx_id": target.id,
                    "type": target.type,
                    "connectors": {
                        "ami": bool(target.ami),
                        "ari": bool(target.ari),
                        "esl": bool(target.esl),
                    },
                    "secrets_ready": len(missing_env) == 0,
                    "missing_env": sorted(set(missing_env)),
                }
            )

        platform_types = {target.type for target in self.settings.targets}
        unsupported_tool_families = sorted(
            {"asterisk", "freeswitch"} - platform_types
        )
        data = {
            "server": "telecom-mcp",
            "runtime_build": self._runtime_build_info(),
            "mode": self.mode.value,
            "transport": self.runtime_flags.transport,
            "fixtures": self.runtime_flags.fixtures,
            "real_backend": self.runtime_flags.real_pbx,
            "live_connector_mode_effective": True,
            "fixture_mode_semantics": {
                "core_tools_use_live_connectors": True,
                "requires_mock_injection": True,
            },
            "targets_count": len(self.settings.targets),
            "effective_targets_file": self.effective_targets_file,
            "targets_file_source": self.targets_file_source,
            "startup_warnings": self.startup_warnings,
            "preflight": {
                "platform_coverage": {
                    "configured": sorted(platform_types),
                    "missing": unsupported_tool_families,
                },
                "targets": target_capabilities,
                "tool_availability": {
                    "exported_families": ["telecom", "asterisk", "freeswitch"],
                    "unsupported_families_for_current_targets": unsupported_tool_families,
                    "requires_target_type": {
                        "telecom.healthcheck": [],
                        "telecom.list_targets": [],
                        "telecom.summary": ["asterisk", "freeswitch"],
                        "telecom.capture_snapshot": ["asterisk", "freeswitch"],
                        "telecom.endpoints": ["asterisk", "freeswitch"],
                        "telecom.registrations": ["asterisk", "freeswitch"],
                        "telecom.channels": ["asterisk", "freeswitch"],
                        "telecom.calls": ["asterisk", "freeswitch"],
                        "telecom.logs": ["asterisk", "freeswitch"],
                        "telecom.inventory": ["asterisk", "freeswitch"],
                        "telecom.diff_snapshots": [],
                        "telecom.compare_targets": [],
                        "telecom.run_smoke_test": ["asterisk", "freeswitch"],
                        "telecom.run_playbook": ["asterisk", "freeswitch"],
                        "telecom.run_smoke_suite": ["asterisk", "freeswitch"],
                        "telecom.baseline_create": ["asterisk", "freeswitch"],
                        "telecom.baseline_show": [],
                        "telecom.audit_target": ["asterisk", "freeswitch"],
                        "telecom.drift_target_vs_baseline": ["asterisk", "freeswitch"],
                        "telecom.drift_compare_targets": [],
                        "telecom.audit_report": ["asterisk", "freeswitch"],
                        "telecom.audit_export": ["asterisk", "freeswitch"],
                        "telecom.scorecard_target": ["asterisk", "freeswitch"],
                        "telecom.scorecard_cluster": [],
                        "telecom.scorecard_environment": [],
                        "telecom.scorecard_compare": [],
                        "telecom.scorecard_trend": [],
                        "telecom.scorecard_export": [],
                        "telecom.scorecard_policy_inputs": [],
                        "telecom.capture_incident_evidence": ["asterisk", "freeswitch"],
                        "telecom.generate_evidence_pack": ["asterisk", "freeswitch"],
                        "telecom.reconstruct_incident_timeline": [],
                        "telecom.export_evidence_pack": [],
                        "telecom.list_probes": [],
                        "telecom.run_probe": ["asterisk", "freeswitch"],
                        "telecom.list_chaos_scenarios": [],
                        "telecom.run_chaos_scenario": ["asterisk", "freeswitch"],
                        "telecom.list_self_healing_policies": [],
                        "telecom.evaluate_self_healing": ["asterisk", "freeswitch"],
                        "telecom.run_self_healing_policy": ["asterisk", "freeswitch"],
                        "telecom.release_gate_decision": ["asterisk", "freeswitch"],
                        "telecom.release_promotion_decision": [],
                        "telecom.release_gate_history": [],
                        "telecom.assert_state": ["asterisk", "freeswitch"],
                        "telecom.run_registration_probe": ["asterisk", "freeswitch"],
                        "telecom.run_trunk_probe": ["asterisk", "freeswitch"],
                        "telecom.verify_cleanup": ["asterisk", "freeswitch"],
                        "asterisk.health": ["asterisk"],
                        "asterisk.pjsip_show_endpoint": ["asterisk"],
                        "asterisk.pjsip_show_endpoints": ["asterisk"],
                        "asterisk.pjsip_show_registration": ["asterisk"],
                        "asterisk.pjsip_show_contacts": ["asterisk"],
                        "asterisk.active_channels": ["asterisk"],
                        "asterisk.bridges": ["asterisk"],
                        "asterisk.channel_details": ["asterisk"],
                        "asterisk.core_show_channel": ["asterisk"],
                        "asterisk.version": ["asterisk"],
                        "asterisk.modules": ["asterisk"],
                        "asterisk.logs": ["asterisk"],
                        "asterisk.cli": ["asterisk"],
                        "asterisk.originate_probe": ["asterisk"],
                        "asterisk.reload_pjsip": ["asterisk"],
                        "freeswitch.health": ["freeswitch"],
                        "freeswitch.sofia_status": ["freeswitch"],
                        "freeswitch.registrations": ["freeswitch"],
                        "freeswitch.gateway_status": ["freeswitch"],
                        "freeswitch.channels": ["freeswitch"],
                        "freeswitch.calls": ["freeswitch"],
                        "freeswitch.channel_details": ["freeswitch"],
                        "freeswitch.version": ["freeswitch"],
                        "freeswitch.modules": ["freeswitch"],
                        "freeswitch.logs": ["freeswitch"],
                        "freeswitch.api": ["freeswitch"],
                        "freeswitch.originate_probe": ["freeswitch"],
                        "freeswitch.reloadxml": ["freeswitch"],
                        "freeswitch.sofia_profile_rescan": ["freeswitch"],
                    },
                },
            },
            "policy": {
                "write_allowlist": list(self.settings.write_allowlist),
                "cooldown_seconds": self.settings.cooldown_seconds,
                "max_calls_per_window": self.settings.max_calls_per_window,
                "rate_limit_window_seconds": self.settings.rate_limit_window_seconds,
                "tool_timeout_seconds": self.settings.tool_timeout_seconds,
                "write_mode_active": self.mode in {Mode.EXECUTE_SAFE, Mode.EXECUTE_FULL},
                "writes_effectively_disabled": (
                    self.mode in {Mode.INSPECT, Mode.PLAN}
                    or len(self.settings.write_allowlist) == 0
                ),
                "require_explicit_targets_file": self.runtime_flags.require_explicit_targets_file,
                "require_confirm_token": os.getenv(
                    "TELECOM_MCP_REQUIRE_CONFIRM_TOKEN", ""
                ).strip()
                == "1",
                "runtime_flag_require_confirm_token": self.runtime_flags.require_confirm_token,
                "require_authenticated_caller": _require_authenticated_caller_effective(),
                "auth_token_configured": bool(
                    os.getenv("TELECOM_MCP_AUTH_TOKEN", "").strip()
                ),
                "enforce_target_policy": os.getenv(
                    "TELECOM_MCP_ENFORCE_TARGET_POLICY", ""
                ).strip()
                == "1",
                "strict_state_persistence": os.getenv(
                    "TELECOM_MCP_STRICT_STATE_PERSISTENCE", ""
                ).strip()
                == "1",
                "fail_on_degraded_default": os.getenv(
                    "TELECOM_MCP_FAIL_ON_DEGRADED_DEFAULT", ""
                ).strip()
                == "1",
                "allowed_capability_classes": sorted(
                    self.core_server.allowed_capability_classes
                ),
                "capability_class_by_tool": dict(
                    sorted(self.core_server.tool_capability_class.items())
                ),
            },
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
        def telecom_summary(
            pbx_id: str,
            fail_on_degraded: bool = False,
        ) -> dict[str, Any]:
            """Return normalized one-call summary for a target."""
            args: dict[str, Any] = {"pbx_id": pbx_id}
            if fail_on_degraded:
                args["fail_on_degraded"] = True
            return self._execute("telecom.summary", args)

        @self.app.tool(name="telecom.capture_snapshot")
        def telecom_capture_snapshot(
            pbx_id: str,
            include: SnapshotInclude | str | None = None,
            limits: SnapshotLimits | str | None = None,
            fail_on_degraded: bool = False,
        ) -> dict[str, Any]:
            """Capture bounded troubleshooting evidence; use fail_on_degraded=true for strict failures."""
            args: dict[str, Any] = {"pbx_id": pbx_id}
            if fail_on_degraded:
                args["fail_on_degraded"] = True
            if include is not None:
                args["include"] = _coerce_include_arg(include)
            if limits is not None:
                args["limits"] = _coerce_limits_arg(limits)
            return self._execute("telecom.capture_snapshot", args)

        @self.app.tool(name="telecom.endpoints")
        def telecom_endpoints(
            pbx_id: str,
            filter: EndpointFilter | str | None = None,
            limit: int | str = 200,
        ) -> dict[str, Any]:
            """List normalized telecom endpoints."""
            args: dict[str, Any] = {"pbx_id": pbx_id, "limit": _coerce_positive_int(limit)}
            if filter is not None:
                args["filter"] = _coerce_object_arg(filter)
            return self._execute("telecom.endpoints", args)

        @self.app.tool(name="telecom.registrations")
        def telecom_registrations(
            pbx_id: str,
            limit: int | str = 200,
        ) -> dict[str, Any]:
            """List normalized telecom registrations."""
            return self._execute(
                "telecom.registrations",
                {"pbx_id": pbx_id, "limit": _coerce_positive_int(limit)},
            )

        @self.app.tool(name="telecom.channels")
        def telecom_channels(pbx_id: str, limit: int | str = 200) -> dict[str, Any]:
            """List normalized telecom channels."""
            return self._execute(
                "telecom.channels",
                {"pbx_id": pbx_id, "limit": _coerce_positive_int(limit)},
            )

        @self.app.tool(name="telecom.calls")
        def telecom_calls(pbx_id: str, limit: int | str = 200) -> dict[str, Any]:
            """List normalized telecom calls."""
            return self._execute(
                "telecom.calls",
                {"pbx_id": pbx_id, "limit": _coerce_positive_int(limit)},
            )

        @self.app.tool(name="telecom.logs")
        def telecom_logs(
            pbx_id: str,
            grep: str | None = None,
            tail: int | str = 200,
            level: str | None = None,
        ) -> dict[str, Any]:
            """List normalized telecom logs with bounded tail and optional grep/level."""
            args: dict[str, Any] = {"pbx_id": pbx_id, "tail": _coerce_positive_int(tail)}
            if isinstance(grep, str) and grep.strip():
                args["grep"] = grep
            if isinstance(level, str) and level.strip():
                args["level"] = level
            return self._execute("telecom.logs", args)

        @self.app.tool(name="telecom.inventory")
        def telecom_inventory(pbx_id: str) -> dict[str, Any]:
            """Collect normalized target inventory."""
            return self._execute("telecom.inventory", {"pbx_id": pbx_id})

        @self.app.tool(name="telecom.diff_snapshots")
        def telecom_diff_snapshots(
            snapshot_a: SnapshotPayload | str,
            snapshot_b: SnapshotPayload | str,
        ) -> dict[str, Any]:
            """Diff two snapshot payloads and return normalized changes."""
            return self._execute(
                "telecom.diff_snapshots",
                {
                    "snapshot_a": _coerce_object_arg(snapshot_a),
                    "snapshot_b": _coerce_object_arg(snapshot_b),
                },
            )

        @self.app.tool(name="telecom.compare_targets")
        def telecom_compare_targets(pbx_a: str, pbx_b: str) -> dict[str, Any]:
            """Compare normalized inventory posture across two targets."""
            return self._execute(
                "telecom.compare_targets",
                {"pbx_a": pbx_a, "pbx_b": pbx_b},
            )

        @self.app.tool(name="telecom.run_smoke_test")
        def telecom_run_smoke_test(pbx_id: str) -> dict[str, Any]:
            """Run a bounded read-only smoke suite for a target."""
            return self._execute("telecom.run_smoke_test", {"pbx_id": pbx_id})

        @self.app.tool(name="telecom.run_playbook")
        def telecom_run_playbook(
            name: str,
            pbx_id: str | None = None,
            endpoint: str | None = None,
            pbx_a: str | None = None,
            pbx_b: str | None = None,
            params: dict[str, Any] | str | None = None,
        ) -> dict[str, Any]:
            """Run a deterministic troubleshooting playbook."""
            args: dict[str, Any] = {"name": name}
            if isinstance(pbx_id, str) and pbx_id.strip():
                args["pbx_id"] = pbx_id.strip()
            if isinstance(endpoint, str) and endpoint.strip():
                args["endpoint"] = endpoint.strip()
            if isinstance(pbx_a, str) and pbx_a.strip():
                args["pbx_a"] = pbx_a.strip()
            if isinstance(pbx_b, str) and pbx_b.strip():
                args["pbx_b"] = pbx_b.strip()
            if params is not None:
                args["params"] = _coerce_object_arg(params)
            return self._execute("telecom.run_playbook", args)

        @self.app.tool(name="telecom.run_smoke_suite")
        def telecom_run_smoke_suite(
            name: str,
            pbx_id: str,
            params: dict[str, Any] | str | None = None,
        ) -> dict[str, Any]:
            """Run a deterministic smoke suite."""
            args: dict[str, Any] = {"name": name, "pbx_id": pbx_id}
            if params is not None:
                args["params"] = _coerce_object_arg(params)
            return self._execute("telecom.run_smoke_suite", args)

        @self.app.tool(name="telecom.baseline_create")
        def telecom_baseline_create(
            pbx_id: str, baseline_id: str | None = None
        ) -> dict[str, Any]:
            """Create a baseline from current target state."""
            args: dict[str, Any] = {"pbx_id": pbx_id}
            if isinstance(baseline_id, str) and baseline_id.strip():
                args["baseline_id"] = baseline_id.strip()
            return self._execute("telecom.baseline_create", args)

        @self.app.tool(name="telecom.baseline_show")
        def telecom_baseline_show(baseline_id: str) -> dict[str, Any]:
            """Show a previously created baseline."""
            return self._execute("telecom.baseline_show", {"baseline_id": baseline_id})

        @self.app.tool(name="telecom.audit_target")
        def telecom_audit_target(
            pbx_id: str, baseline_id: str | None = None
        ) -> dict[str, Any]:
            """Run baseline-driven audit for one target."""
            args: dict[str, Any] = {"pbx_id": pbx_id}
            if isinstance(baseline_id, str) and baseline_id.strip():
                args["baseline_id"] = baseline_id.strip()
            return self._execute("telecom.audit_target", args)

        @self.app.tool(name="telecom.drift_target_vs_baseline")
        def telecom_drift_target_vs_baseline(
            pbx_id: str, baseline_id: str
        ) -> dict[str, Any]:
            """Compare live target state to a baseline."""
            return self._execute(
                "telecom.drift_target_vs_baseline",
                {"pbx_id": pbx_id, "baseline_id": baseline_id},
            )

        @self.app.tool(name="telecom.drift_compare_targets")
        def telecom_drift_compare_targets(pbx_a: str, pbx_b: str) -> dict[str, Any]:
            """Compare drift indicators between two targets."""
            return self._execute(
                "telecom.drift_compare_targets",
                {"pbx_a": pbx_a, "pbx_b": pbx_b},
            )

        @self.app.tool(name="telecom.audit_report")
        def telecom_audit_report(
            pbx_id: str, baseline_id: str | None = None
        ) -> dict[str, Any]:
            """Generate structured audit report for one target."""
            args: dict[str, Any] = {"pbx_id": pbx_id}
            if isinstance(baseline_id, str) and baseline_id.strip():
                args["baseline_id"] = baseline_id.strip()
            return self._execute("telecom.audit_report", args)

        @self.app.tool(name="telecom.audit_export")
        def telecom_audit_export(
            pbx_id: str, format: str = "json", baseline_id: str | None = None
        ) -> dict[str, Any]:
            """Export audit report payload as JSON or Markdown."""
            args: dict[str, Any] = {"pbx_id": pbx_id, "format": format}
            if isinstance(baseline_id, str) and baseline_id.strip():
                args["baseline_id"] = baseline_id.strip()
            return self._execute("telecom.audit_export", args)

        @self.app.tool(name="telecom.scorecard_target")
        def telecom_scorecard_target(pbx_id: str) -> dict[str, Any]:
            """Generate PBX resilience scorecard."""
            return self._execute("telecom.scorecard_target", {"pbx_id": pbx_id})

        @self.app.tool(name="telecom.scorecard_cluster")
        def telecom_scorecard_cluster(
            cluster_id: str, pbx_ids: list[str] | str
        ) -> dict[str, Any]:
            """Generate cluster resilience scorecard from PBX members."""
            args: dict[str, Any] = {"cluster_id": cluster_id}
            if isinstance(pbx_ids, str):
                args["pbx_ids"] = [item.strip() for item in pbx_ids.split(",") if item.strip()]
            elif isinstance(pbx_ids, list):
                args["pbx_ids"] = [str(item).strip() for item in pbx_ids if str(item).strip()]
            else:
                raise ToolError(VALIDATION_ERROR, "Field 'pbx_ids' must be list or comma-separated string")
            return self._execute("telecom.scorecard_cluster", args)

        @self.app.tool(name="telecom.scorecard_environment")
        def telecom_scorecard_environment(
            environment_id: str, pbx_ids: list[str] | str | None = None
        ) -> dict[str, Any]:
            """Generate environment resilience scorecard."""
            args: dict[str, Any] = {"environment_id": environment_id}
            if isinstance(pbx_ids, str):
                args["pbx_ids"] = [item.strip() for item in pbx_ids.split(",") if item.strip()]
            elif isinstance(pbx_ids, list):
                args["pbx_ids"] = [str(item).strip() for item in pbx_ids if str(item).strip()]
            return self._execute("telecom.scorecard_environment", args)

        @self.app.tool(name="telecom.scorecard_compare")
        def telecom_scorecard_compare(
            entity_a: str,
            entity_b: str,
            entity_type: str = "pbx",
            pbx_ids_a: list[str] | str | None = None,
            pbx_ids_b: list[str] | str | None = None,
        ) -> dict[str, Any]:
            """Compare two resilience scorecards."""
            args: dict[str, Any] = {
                "entity_type": entity_type,
                "entity_a": entity_a,
                "entity_b": entity_b,
            }
            if isinstance(pbx_ids_a, str):
                args["pbx_ids_a"] = [item.strip() for item in pbx_ids_a.split(",") if item.strip()]
            elif isinstance(pbx_ids_a, list):
                args["pbx_ids_a"] = [str(item).strip() for item in pbx_ids_a if str(item).strip()]
            if isinstance(pbx_ids_b, str):
                args["pbx_ids_b"] = [item.strip() for item in pbx_ids_b.split(",") if item.strip()]
            elif isinstance(pbx_ids_b, list):
                args["pbx_ids_b"] = [str(item).strip() for item in pbx_ids_b if str(item).strip()]
            return self._execute("telecom.scorecard_compare", args)

        @self.app.tool(name="telecom.scorecard_trend")
        def telecom_scorecard_trend(
            entity_type: str, entity_id: str, window: str = "30d"
        ) -> dict[str, Any]:
            """Summarize scorecard trend changes."""
            return self._execute(
                "telecom.scorecard_trend",
                {"entity_type": entity_type, "entity_id": entity_id, "window": window},
            )

        @self.app.tool(name="telecom.scorecard_export")
        def telecom_scorecard_export(
            entity_type: str,
            entity_id: str,
            format: str = "json",
            pbx_ids: list[str] | str | None = None,
        ) -> dict[str, Any]:
            """Export scorecard as JSON or Markdown."""
            args: dict[str, Any] = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "format": format,
            }
            if isinstance(pbx_ids, str):
                args["pbx_ids"] = [item.strip() for item in pbx_ids.split(",") if item.strip()]
            elif isinstance(pbx_ids, list):
                args["pbx_ids"] = [str(item).strip() for item in pbx_ids if str(item).strip()]
            return self._execute("telecom.scorecard_export", args)

        @self.app.tool(name="telecom.scorecard_policy_inputs")
        def telecom_scorecard_policy_inputs(
            entity_type: str = "pbx",
            entity_id: str | None = None,
            pbx_id: str | None = None,
            pbx_ids: list[str] | str | None = None,
            scorecard: dict[str, Any] | str | None = None,
        ) -> dict[str, Any]:
            """Build safe self-healing policy input hints from scorecards."""
            args: dict[str, Any] = {"entity_type": entity_type}
            if isinstance(entity_id, str) and entity_id.strip():
                args["entity_id"] = entity_id.strip()
            if isinstance(pbx_id, str) and pbx_id.strip():
                args["pbx_id"] = pbx_id.strip()
            if isinstance(pbx_ids, str):
                args["pbx_ids"] = [item.strip() for item in pbx_ids.split(",") if item.strip()]
            elif isinstance(pbx_ids, list):
                args["pbx_ids"] = [str(item).strip() for item in pbx_ids if str(item).strip()]
            if scorecard is not None:
                args["scorecard"] = _coerce_object_arg(scorecard)
            return self._execute("telecom.scorecard_policy_inputs", args)

        @self.app.tool(name="telecom.capture_incident_evidence")
        def telecom_capture_incident_evidence(pbx_id: str) -> dict[str, Any]:
            """Collect evidence slices for incident forensics."""
            return self._execute("telecom.capture_incident_evidence", {"pbx_id": pbx_id})

        @self.app.tool(name="telecom.generate_evidence_pack")
        def telecom_generate_evidence_pack(
            pbx_id: str,
            incident_type: str = "unspecified_incident",
            incident_id: str | None = None,
            collector: str | None = None,
            collection_mode: str | None = None,
        ) -> dict[str, Any]:
            """Generate structured incident evidence pack."""
            args: dict[str, Any] = {"pbx_id": pbx_id, "incident_type": incident_type}
            if isinstance(incident_id, str) and incident_id.strip():
                args["incident_id"] = incident_id.strip()
            if isinstance(collector, str) and collector.strip():
                args["collector"] = collector.strip()
            if isinstance(collection_mode, str) and collection_mode.strip():
                args["collection_mode"] = collection_mode.strip()
            return self._execute("telecom.generate_evidence_pack", args)

        @self.app.tool(name="telecom.reconstruct_incident_timeline")
        def telecom_reconstruct_incident_timeline(pack_id: str) -> dict[str, Any]:
            """Reconstruct event timeline from collected evidence pack."""
            return self._execute(
                "telecom.reconstruct_incident_timeline",
                {"pack_id": pack_id},
            )

        @self.app.tool(name="telecom.export_evidence_pack")
        def telecom_export_evidence_pack(
            pack_id: str, format: str = "json"
        ) -> dict[str, Any]:
            """Export evidence pack as JSON, Markdown, or ZIP-manifest payload."""
            return self._execute(
                "telecom.export_evidence_pack",
                {"pack_id": pack_id, "format": format},
            )

        @self.app.tool(name="telecom.list_probes")
        def telecom_list_probes() -> dict[str, Any]:
            """List available validation probes and metadata."""
            return self._execute("telecom.list_probes", {})

        @self.app.tool(name="telecom.run_probe")
        def telecom_run_probe(
            name: str, pbx_id: str, params: dict[str, Any] | str | None = None
        ) -> dict[str, Any]:
            """Run a gated telecom validation probe."""
            args: dict[str, Any] = {"name": name, "pbx_id": pbx_id}
            if params is not None:
                args["params"] = _coerce_object_arg(params)
            return self._execute("telecom.run_probe", args)

        @self.app.tool(name="telecom.list_chaos_scenarios")
        def telecom_list_chaos_scenarios() -> dict[str, Any]:
            """List available chaos simulation scenarios."""
            return self._execute("telecom.list_chaos_scenarios", {})

        @self.app.tool(name="telecom.run_chaos_scenario")
        def telecom_run_chaos_scenario(
            name: str, pbx_id: str, params: dict[str, Any] | str | None = None
        ) -> dict[str, Any]:
            """Run a gated chaos simulation scenario."""
            args: dict[str, Any] = {"name": name, "pbx_id": pbx_id}
            if params is not None:
                args["params"] = _coerce_object_arg(params)
            return self._execute("telecom.run_chaos_scenario", args)

        @self.app.tool(name="telecom.list_self_healing_policies")
        def telecom_list_self_healing_policies() -> dict[str, Any]:
            """List available self-healing policies."""
            return self._execute("telecom.list_self_healing_policies", {})

        @self.app.tool(name="telecom.evaluate_self_healing")
        def telecom_evaluate_self_healing(
            pbx_id: str, context: dict[str, Any] | str | None = None
        ) -> dict[str, Any]:
            """Evaluate eligible self-healing policies for target context."""
            args: dict[str, Any] = {"pbx_id": pbx_id}
            if context is not None:
                args["context"] = _coerce_object_arg(context)
            return self._execute("telecom.evaluate_self_healing", args)

        @self.app.tool(name="telecom.run_self_healing_policy")
        def telecom_run_self_healing_policy(
            name: str, pbx_id: str, params: dict[str, Any] | str | None = None
        ) -> dict[str, Any]:
            """Run one gated self-healing policy."""
            args: dict[str, Any] = {"name": name, "pbx_id": pbx_id}
            if params is not None:
                args["params"] = _coerce_object_arg(params)
            return self._execute("telecom.run_self_healing_policy", args)

        @self.app.tool(name="telecom.release_gate_decision")
        def telecom_release_gate_decision(
            pbx_id: str,
            context: dict[str, Any] | str | None = None,
            policy_input: dict[str, Any] | str | None = None,
            validation: dict[str, Any] | str | None = None,
        ) -> dict[str, Any]:
            """Evaluate release gate decision from scorecard policy input + validation evidence."""
            args: dict[str, Any] = {"pbx_id": pbx_id}
            if context is not None:
                args["context"] = _coerce_object_arg(context)
            if policy_input is not None:
                args["policy_input"] = _coerce_object_arg(policy_input)
            if validation is not None:
                args["validation"] = _coerce_object_arg(validation)
            return self._execute("telecom.release_gate_decision", args)

        @self.app.tool(name="telecom.release_promotion_decision")
        def telecom_release_promotion_decision(
            environment_id: str,
            pbx_ids: list[str] | str,
            context: dict[str, Any] | str | None = None,
        ) -> dict[str, Any]:
            """Aggregate member release-gate decisions for environment promotion."""
            args: dict[str, Any] = {"environment_id": environment_id}
            if isinstance(pbx_ids, str):
                args["pbx_ids"] = [item.strip() for item in pbx_ids.split(",") if item.strip()]
            elif isinstance(pbx_ids, list):
                args["pbx_ids"] = [str(item).strip() for item in pbx_ids if str(item).strip()]
            else:
                raise ToolError(VALIDATION_ERROR, "Field 'pbx_ids' must be list or comma-separated string")
            if context is not None:
                args["context"] = _coerce_object_arg(context)
            return self._execute("telecom.release_promotion_decision", args)

        @self.app.tool(name="telecom.release_gate_history")
        def telecom_release_gate_history(
            entity_type: str,
            entity_id: str,
            limit: int | str = 20,
        ) -> dict[str, Any]:
            """Return release-gate history and decision trend for an entity."""
            return self._execute(
                "telecom.release_gate_history",
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "limit": _coerce_positive_int(limit),
                },
            )

        @self.app.tool(name="telecom.assert_state")
        def telecom_assert_state(
            pbx_id: str, assertion: str, params: AssertionParams | str | None = None
        ) -> dict[str, Any]:
            """Evaluate a normalized assertion on current target state."""
            args: dict[str, Any] = {"pbx_id": pbx_id, "assertion": assertion}
            if params is not None:
                args["params"] = _coerce_object_arg(params)
            return self._execute("telecom.assert_state", args)

        @self.app.tool(name="telecom.run_registration_probe")
        def telecom_run_registration_probe(
            pbx_id: str,
            destination: str,
            reason: str,
            change_ticket: str,
            timeout_s: int | str = 20,
            confirm_token: str | None = None,
        ) -> dict[str, Any]:
            """Run an active registration probe (execute_safe+ and allowlist required)."""
            args: dict[str, Any] = {
                "pbx_id": pbx_id,
                "destination": destination,
                "timeout_s": _coerce_positive_int(timeout_s),
                "reason": reason.strip() if isinstance(reason, str) else reason,
                "change_ticket": (
                    change_ticket.strip()
                    if isinstance(change_ticket, str)
                    else change_ticket
                ),
            }
            if isinstance(confirm_token, str) and confirm_token.strip():
                args["confirm_token"] = confirm_token.strip()
            return self._execute("telecom.run_registration_probe", args)

        @self.app.tool(name="telecom.run_trunk_probe")
        def telecom_run_trunk_probe(
            pbx_id: str,
            destination: str,
            reason: str,
            change_ticket: str,
            timeout_s: int | str = 20,
            confirm_token: str | None = None,
        ) -> dict[str, Any]:
            """Run an active trunk probe (execute_safe+ and allowlist required)."""
            args: dict[str, Any] = {
                "pbx_id": pbx_id,
                "destination": destination,
                "timeout_s": _coerce_positive_int(timeout_s),
                "reason": reason.strip() if isinstance(reason, str) else reason,
                "change_ticket": (
                    change_ticket.strip()
                    if isinstance(change_ticket, str)
                    else change_ticket
                ),
            }
            if isinstance(confirm_token, str) and confirm_token.strip():
                args["confirm_token"] = confirm_token.strip()
            return self._execute("telecom.run_trunk_probe", args)

        @self.app.tool(name="telecom.verify_cleanup")
        def telecom_verify_cleanup(
            pbx_id: str, probe_id: str | None = None
        ) -> dict[str, Any]:
            """Check for residual probe calls/channels after validation actions."""
            args: dict[str, Any] = {"pbx_id": pbx_id}
            if isinstance(probe_id, str) and probe_id.strip():
                args["probe_id"] = probe_id.strip()
            return self._execute("telecom.verify_cleanup", args)

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
            filter: EndpointFilter | str | None = None,
            limit: int | str = 200,
        ) -> dict[str, Any]:
            """List PJSIP endpoints with optional filters."""
            args: dict[str, Any] = {
                "pbx_id": pbx_id,
                "limit": _coerce_positive_int(limit),
            }
            if filter is not None:
                args["filter"] = _coerce_object_arg(filter)
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

        @self.app.tool(name="asterisk.pjsip_show_contacts")
        def asterisk_pjsip_show_contacts(
            pbx_id: str,
            filter: EndpointFilter | str | None = None,
            limit: int | str = 200,
        ) -> dict[str, Any]:
            """List PJSIP contacts with optional filters."""
            args: dict[str, Any] = {
                "pbx_id": pbx_id,
                "limit": _coerce_positive_int(limit),
            }
            if filter is not None:
                args["filter"] = _coerce_object_arg(filter)
            return self._execute("asterisk.pjsip_show_contacts", args)

        @self.app.tool(name="asterisk.active_channels")
        def asterisk_active_channels(
            pbx_id: str,
            filter: ActiveChannelFilter | str | None = None,
            limit: int | str = 200,
        ) -> dict[str, Any]:
            """List active channels with optional filters."""
            args: dict[str, Any] = {
                "pbx_id": pbx_id,
                "limit": _coerce_positive_int(limit),
            }
            if filter is not None:
                args["filter"] = _coerce_object_arg(filter)
            return self._execute("asterisk.active_channels", args)

        @self.app.tool(name="asterisk.bridges")
        def asterisk_bridges(pbx_id: str, limit: int | str = 200) -> dict[str, Any]:
            """List active bridges."""
            return self._execute(
                "asterisk.bridges",
                {"pbx_id": pbx_id, "limit": _coerce_positive_int(limit)},
            )

        @self.app.tool(name="asterisk.channel_details")
        def asterisk_channel_details(pbx_id: str, channel_id: str) -> dict[str, Any]:
            """Get details for a specific channel."""
            return self._execute(
                "asterisk.channel_details",
                {"pbx_id": pbx_id, "channel_id": channel_id},
            )

        @self.app.tool(name="asterisk.core_show_channel")
        def asterisk_core_show_channel(pbx_id: str, channel_id: str) -> dict[str, Any]:
            """Get channel details from AMI CoreShowChannels event output."""
            return self._execute(
                "asterisk.core_show_channel",
                {"pbx_id": pbx_id, "channel_id": channel_id},
            )

        @self.app.tool(name="asterisk.version")
        def asterisk_version(pbx_id: str) -> dict[str, Any]:
            """Get Asterisk version."""
            return self._execute("asterisk.version", {"pbx_id": pbx_id})

        @self.app.tool(name="asterisk.modules")
        def asterisk_modules(pbx_id: str) -> dict[str, Any]:
            """Get Asterisk module inventory."""
            return self._execute("asterisk.modules", {"pbx_id": pbx_id})

        @self.app.tool(name="asterisk.logs")
        def asterisk_logs(
            pbx_id: str,
            grep: str | None = None,
            tail: int | str = 200,
            level: str | None = None,
        ) -> dict[str, Any]:
            """Read Asterisk logs from configured log source."""
            args: dict[str, Any] = {"pbx_id": pbx_id, "tail": _coerce_positive_int(tail)}
            if isinstance(grep, str) and grep.strip():
                args["grep"] = grep
            if isinstance(level, str) and level.strip():
                args["level"] = level
            return self._execute("asterisk.logs", args)

        @self.app.tool(name="asterisk.cli")
        def asterisk_cli(pbx_id: str, command: str) -> dict[str, Any]:
            """Run an allowlisted read-only Asterisk CLI command via AMI Command."""
            return self._execute(
                "asterisk.cli",
                {"pbx_id": pbx_id, "command": command},
            )

        @self.app.tool(name="asterisk.originate_probe")
        def asterisk_originate_probe(
            pbx_id: str,
            destination: str,
            reason: str,
            change_ticket: str,
            timeout_s: int | str = 20,
            confirm_token: str | None = None,
        ) -> dict[str, Any]:
            """Run an active originate probe on Asterisk (execute_safe+ and allowlist required)."""
            args: dict[str, Any] = {
                "pbx_id": pbx_id,
                "destination": destination,
                "timeout_s": _coerce_positive_int(timeout_s),
                "reason": reason.strip() if isinstance(reason, str) else reason,
                "change_ticket": (
                    change_ticket.strip()
                    if isinstance(change_ticket, str)
                    else change_ticket
                ),
            }
            if isinstance(confirm_token, str) and confirm_token.strip():
                args["confirm_token"] = confirm_token.strip()
            return self._execute("asterisk.originate_probe", args)

        @self.app.tool(name="asterisk.reload_pjsip")
        def asterisk_reload_pjsip(
            pbx_id: str,
            reason: str,
            change_ticket: str,
            confirm_token: str | None = None,
        ) -> dict[str, Any]:
            """Reload PJSIP module (requires execute_safe+, reason/change_ticket, optional confirm_token)."""
            args: dict[str, Any] = {"pbx_id": pbx_id}
            args["reason"] = reason.strip() if isinstance(reason, str) else reason
            args["change_ticket"] = (
                change_ticket.strip()
                if isinstance(change_ticket, str)
                else change_ticket
            )
            if isinstance(confirm_token, str) and confirm_token.strip():
                args["confirm_token"] = confirm_token.strip()
            return self._execute("asterisk.reload_pjsip", args)

        @self.app.tool(name="freeswitch.health")
        def freeswitch_health(
            pbx_id: str,
            include_raw: bool = False,
        ) -> dict[str, Any]:
            """Check FreeSWITCH ESL health."""
            return self._execute(
                "freeswitch.health",
                {"pbx_id": pbx_id, "include_raw": bool(include_raw)},
            )

        @self.app.tool(name="freeswitch.capabilities")
        def freeswitch_capabilities(
            pbx_id: str,
            include_raw: bool = False,
        ) -> dict[str, Any]:
            """Inspect machine-readable FreeSWITCH target capabilities."""
            return self._execute(
                "freeswitch.capabilities",
                {"pbx_id": pbx_id, "include_raw": bool(include_raw)},
            )

        @self.app.tool(name="freeswitch.recent_events")
        def freeswitch_recent_events(
            pbx_id: str,
            limit: int | str = 20,
            event_names: list[str] | str | None = None,
            event_family: str | None = None,
            include_raw: bool = False,
        ) -> dict[str, Any]:
            """Read recent passive FreeSWITCH events from the bounded in-memory buffer."""
            args: dict[str, Any] = {
                "pbx_id": pbx_id,
                "limit": _coerce_positive_int(limit),
                "include_raw": bool(include_raw),
            }
            if isinstance(event_names, str):
                args["event_names"] = [item.strip() for item in event_names.split(",") if item.strip()]
            elif isinstance(event_names, list):
                args["event_names"] = [str(item).strip() for item in event_names if str(item).strip()]
            if isinstance(event_family, str) and event_family.strip():
                args["event_family"] = event_family.strip()
            return self._execute("freeswitch.recent_events", args)

        @self.app.tool(name="freeswitch.sofia_status")
        def freeswitch_sofia_status(
            pbx_id: str,
            profile: str | None = None,
            include_raw: bool = False,
        ) -> dict[str, Any]:
            """Get sofia status with optional profile."""
            args: dict[str, Any] = {"pbx_id": pbx_id}
            if isinstance(profile, str) and profile:
                args["profile"] = profile
            args["include_raw"] = bool(include_raw)
            return self._execute("freeswitch.sofia_status", args)

        @self.app.tool(name="freeswitch.registrations")
        def freeswitch_registrations(
            pbx_id: str,
            profile: str | None = None,
            limit: int | str = 200,
            include_raw: bool = False,
        ) -> dict[str, Any]:
            """List FreeSWITCH registrations."""
            args: dict[str, Any] = {
                "pbx_id": pbx_id,
                "limit": _coerce_positive_int(limit),
                "include_raw": bool(include_raw),
            }
            if isinstance(profile, str) and profile:
                args["profile"] = profile
            return self._execute("freeswitch.registrations", args)

        @self.app.tool(name="freeswitch.gateway_status")
        def freeswitch_gateway_status(
            pbx_id: str,
            gateway: str,
            include_raw: bool = False,
        ) -> dict[str, Any]:
            """Inspect a FreeSWITCH gateway."""
            return self._execute(
                "freeswitch.gateway_status",
                {"pbx_id": pbx_id, "gateway": gateway, "include_raw": bool(include_raw)},
            )

        @self.app.tool(name="freeswitch.channels")
        def freeswitch_channels(
            pbx_id: str,
            limit: int | str = 200,
            include_raw: bool = False,
        ) -> dict[str, Any]:
            """List FreeSWITCH channels."""
            return self._execute(
                "freeswitch.channels",
                {
                    "pbx_id": pbx_id,
                    "limit": _coerce_positive_int(limit),
                    "include_raw": bool(include_raw),
                },
            )

        @self.app.tool(name="freeswitch.calls")
        def freeswitch_calls(
            pbx_id: str,
            limit: int | str = 200,
            include_raw: bool = False,
        ) -> dict[str, Any]:
            """List FreeSWITCH calls."""
            return self._execute(
                "freeswitch.calls",
                {
                    "pbx_id": pbx_id,
                    "limit": _coerce_positive_int(limit),
                    "include_raw": bool(include_raw),
                },
            )

        @self.app.tool(name="freeswitch.channel_details")
        def freeswitch_channel_details(
            pbx_id: str,
            uuid: str,
            include_raw: bool = False,
        ) -> dict[str, Any]:
            """Get details for a specific FreeSWITCH channel UUID."""
            return self._execute(
                "freeswitch.channel_details",
                {"pbx_id": pbx_id, "uuid": uuid, "include_raw": bool(include_raw)},
            )

        @self.app.tool(name="freeswitch.version")
        def freeswitch_version(
            pbx_id: str,
            include_raw: bool = False,
        ) -> dict[str, Any]:
            """Get FreeSWITCH version."""
            return self._execute(
                "freeswitch.version",
                {"pbx_id": pbx_id, "include_raw": bool(include_raw)},
            )

        @self.app.tool(name="freeswitch.modules")
        def freeswitch_modules(
            pbx_id: str,
            include_raw: bool = False,
        ) -> dict[str, Any]:
            """Get FreeSWITCH module inventory."""
            return self._execute(
                "freeswitch.modules",
                {"pbx_id": pbx_id, "include_raw": bool(include_raw)},
            )

        @self.app.tool(name="freeswitch.logs")
        def freeswitch_logs(
            pbx_id: str,
            grep: str | None = None,
            tail: int | str = 200,
            level: str | None = None,
        ) -> dict[str, Any]:
            """Read FreeSWITCH logs from configured log source."""
            args: dict[str, Any] = {"pbx_id": pbx_id, "tail": _coerce_positive_int(tail)}
            if isinstance(grep, str) and grep.strip():
                args["grep"] = grep
            if isinstance(level, str) and level.strip():
                args["level"] = level
            return self._execute("freeswitch.logs", args)

        @self.app.tool(name="freeswitch.api")
        def freeswitch_api(
            pbx_id: str,
            command: str,
            include_raw: bool = False,
        ) -> dict[str, Any]:
            """Run an allowlisted read-only FreeSWITCH API command."""
            return self._execute(
                "freeswitch.api",
                {"pbx_id": pbx_id, "command": command, "include_raw": bool(include_raw)},
            )

        @self.app.tool(name="freeswitch.originate_probe")
        def freeswitch_originate_probe(
            pbx_id: str,
            destination: str,
            reason: str,
            change_ticket: str,
            timeout_s: int | str = 20,
            confirm_token: str | None = None,
        ) -> dict[str, Any]:
            """Run an active originate probe on FreeSWITCH (execute_safe+ and allowlist required)."""
            args: dict[str, Any] = {
                "pbx_id": pbx_id,
                "destination": destination,
                "timeout_s": _coerce_positive_int(timeout_s),
                "reason": reason.strip() if isinstance(reason, str) else reason,
                "change_ticket": (
                    change_ticket.strip()
                    if isinstance(change_ticket, str)
                    else change_ticket
                ),
            }
            if isinstance(confirm_token, str) and confirm_token.strip():
                args["confirm_token"] = confirm_token.strip()
            return self._execute("freeswitch.originate_probe", args)

        @self.app.tool(name="freeswitch.reloadxml")
        def freeswitch_reloadxml(
            pbx_id: str,
            reason: str,
            change_ticket: str,
            confirm_token: str | None = None,
        ) -> dict[str, Any]:
            """Reload FreeSWITCH XML config (requires execute_safe+, reason/change_ticket, optional confirm_token)."""
            args: dict[str, Any] = {"pbx_id": pbx_id}
            args["reason"] = reason.strip() if isinstance(reason, str) else reason
            args["change_ticket"] = (
                change_ticket.strip()
                if isinstance(change_ticket, str)
                else change_ticket
            )
            if isinstance(confirm_token, str) and confirm_token.strip():
                args["confirm_token"] = confirm_token.strip()
            return self._execute("freeswitch.reloadxml", args)

        @self.app.tool(name="freeswitch.sofia_profile_rescan")
        def freeswitch_sofia_profile_rescan(
            pbx_id: str,
            profile: str,
            reason: str,
            change_ticket: str,
            confirm_token: str | None = None,
        ) -> dict[str, Any]:
            """Rescan a FreeSWITCH sofia profile (requires execute_safe+, reason/change_ticket, optional confirm_token)."""
            args: dict[str, Any] = {"pbx_id": pbx_id, "profile": profile}
            args["reason"] = reason.strip() if isinstance(reason, str) else reason
            args["change_ticket"] = (
                change_ticket.strip()
                if isinstance(change_ticket, str)
                else change_ticket
            )
            if isinstance(confirm_token, str) and confirm_token.strip():
                args["confirm_token"] = confirm_token.strip()
            return self._execute("freeswitch.sofia_profile_rescan", args)

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
        transport = self.runtime_flags.transport
        if transport == "stdio":
            preflight_error = self._stdio_preflight_error()
            if preflight_error is not None:
                sys.stderr.write(json.dumps(preflight_error) + "\n")
                sys.stderr.flush()
                return
            try:
                import anyio

                anyio.run(self._run_stdio_async)
            except BrokenPipeError:
                return
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
        stdin_fd = sys.stdin.fileno()
        stdout_fd = sys.stdout.fileno()

        async def stdin_reader() -> None:
            buffer = b""
            async with read_writer:
                while True:
                    try:
                        await anyio.wait_readable(stdin_fd)
                        chunk = os.read(stdin_fd, 65536)
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
                    if not chunk:
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        raw_line, buffer = buffer.split(b"\n", 1)
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        try:
                            message = mcp_types.JSONRPCMessage.model_validate_json(line)
                        except Exception as exc:
                            await read_writer.send(exc)
                            continue
                        await read_writer.send(SessionMessage(message))

        async def stdout_writer() -> None:
            async with write_reader:
                async for session_message in write_reader:
                    payload = (
                        session_message.message.model_dump_json(
                            by_alias=True,
                            exclude_none=True,
                        )
                        + "\n"
                    )
                    encoded = payload.encode("utf-8")
                    try:
                        await anyio.wait_writable(stdout_fd)
                        os.write(stdout_fd, encoded)
                    except (BrokenPipeError, OSError):
                        return

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
    parser.add_argument("--cooldown-seconds", type=int, default=30)
    parser.add_argument("--max-calls-per-window", type=int, default=200)
    parser.add_argument("--rate-limit-window-seconds", type=float, default=1.0)
    parser.add_argument("--tool-timeout-seconds", type=float, default=5.0)
    parser.add_argument(
        "--strict-startup",
        action="store_true",
        help="Fail startup when key warnings are present (duplicates, missing secrets, coverage gaps).",
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
            strict_startup=flags.strict_startup,
            require_explicit_targets_file=flags.require_explicit_targets_file,
            require_confirm_token=flags.require_confirm_token,
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
            cooldown_seconds=args.cooldown_seconds,
            max_calls_per_window=args.max_calls_per_window,
            rate_limit_window_seconds=args.rate_limit_window_seconds,
            tool_timeout_seconds=args.tool_timeout_seconds,
            strict_startup=args.strict_startup,
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
