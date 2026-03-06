"""Configuration loading for telecom targets and runtime policy."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .authz import Mode, parse_mode
from .errors import AUTH_FAILED, NOT_FOUND, VALIDATION_ERROR, ToolError

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None


@dataclass(slots=True)
class AMIConfig:
    host: str
    port: int
    username_env: str
    password_env: str


@dataclass(slots=True)
class ARIConfig:
    url: str
    username_env: str
    password_env: str
    app: str


@dataclass(slots=True)
class ESLConfig:
    host: str
    port: int
    password_env: str


@dataclass(slots=True)
class LogConfig:
    path: str
    source_command: str | None = None


@dataclass(slots=True)
class TargetConfig:
    id: str
    type: str
    host: str
    environment: str = "unknown"
    safety_tier: str = "standard"
    allow_active_validation: bool = False
    ami: AMIConfig | None = None
    ari: ARIConfig | None = None
    esl: ESLConfig | None = None
    logs: LogConfig | None = None


@dataclass(slots=True)
class Settings:
    targets: list[TargetConfig]
    mode: Mode = Mode.INSPECT
    write_allowlist: list[str] = field(default_factory=list)
    cooldown_seconds: int = 30
    max_calls_per_window: int = 200
    rate_limit_window_seconds: float = 1.0
    tool_timeout_seconds: float = 5.0

    @property
    def target_index(self) -> dict[str, TargetConfig]:
        return {t.id: t for t in self.targets}

    def get_target(self, pbx_id: str) -> TargetConfig:
        target = self.target_index.get(pbx_id)
        if not target:
            raise ToolError(
                NOT_FOUND, f"Target not found: {pbx_id}", {"pbx_id": pbx_id}
            )
        return target


def _parse_scalar(value: str) -> Any:
    raw = value.strip()
    if not raw:
        return ""
    if raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        return raw


def _parse_targets_yaml_legacy(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if not any(line.strip().startswith("targets:") for line in lines):
        raise ToolError(
            VALIDATION_ERROR, "targets.yaml must contain top-level 'targets:' key"
        )

    targets: list[dict[str, Any]] = []
    current_target: dict[str, Any] | None = None
    current_section: dict[str, Any] | None = None

    for line_no, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue

        if "\t" in line:
            raise ToolError(
                VALIDATION_ERROR,
                f"Invalid indentation (tab) in targets file at line {line_no}",
            )

        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)

        if stripped == "targets:":
            continue

        if indent not in {0, 2, 4, 6}:
            raise ToolError(
                VALIDATION_ERROR,
                f"Unsupported indentation depth in targets file at line {line_no}",
            )

        if stripped.startswith("- "):
            payload = stripped[2:]
            if not payload or ":" not in payload:
                raise ToolError(
                    VALIDATION_ERROR,
                    f"Invalid list item in targets file at line {line_no}: {raw}",
                )
            key, value = payload.split(":", 1)
            current_target = {key.strip(): _parse_scalar(value)}
            targets.append(current_target)
            current_section = None
            continue

        if current_target is None:
            raise ToolError(
                VALIDATION_ERROR,
                f"Unexpected line outside of targets list at line {line_no}",
            )

        if ":" not in stripped:
            raise ToolError(
                VALIDATION_ERROR,
                f"Invalid key/value entry in targets file at line {line_no}: {raw}",
            )

        if indent <= 4 and (current_section is None or indent == 4):
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not value:
                section: dict[str, Any] = {}
                current_target[key] = section
                current_section = section
            else:
                current_target[key] = _parse_scalar(value)
                current_section = None
            continue

        if current_section is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            current_section[key.strip()] = _parse_scalar(value)
            continue

        raise ToolError(
            VALIDATION_ERROR,
            f"Unsupported nested structure in targets file at line {line_no}",
        )

    return {"targets": targets}


def _parse_targets_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        try:
            parsed = yaml.safe_load(text)
        except Exception as exc:
            raise ToolError(
                VALIDATION_ERROR,
                f"Failed to parse targets file as YAML: {exc}",
            ) from exc
        if not isinstance(parsed, dict):
            raise ToolError(
                VALIDATION_ERROR,
                "targets.yaml must contain a top-level mapping with 'targets'",
            )
        if "targets" not in parsed:
            raise ToolError(
                VALIDATION_ERROR,
                "targets.yaml must contain top-level 'targets:' key",
            )
        return parsed
    return _parse_targets_yaml_legacy(path)


def resolve_secret_env(env_var_name: str) -> str:
    value = os.getenv(env_var_name)
    if value is None:
        raise ToolError(
            AUTH_FAILED, f"Missing secret environment variable: {env_var_name}"
        )
    return value


def resolve_target_secrets(target: TargetConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": target.id,
        "type": target.type,
        "host": target.host,
    }
    if target.ami:
        payload["ami"] = {
            "host": target.ami.host,
            "port": target.ami.port,
            "username": resolve_secret_env(target.ami.username_env),
            "password": resolve_secret_env(target.ami.password_env),
        }
    if target.ari:
        payload["ari"] = {
            "url": target.ari.url,
            "username": resolve_secret_env(target.ari.username_env),
            "password": resolve_secret_env(target.ari.password_env),
            "app": target.ari.app,
        }
    if target.esl:
        payload["esl"] = {
            "host": target.esl.host,
            "port": target.esl.port,
            "password": resolve_secret_env(target.esl.password_env),
        }
    return payload


def _as_target(raw: dict[str, Any]) -> TargetConfig:
    required = ("id", "type", "host")
    for field_name in required:
        if field_name not in raw or raw[field_name] in (None, ""):
            raise ToolError(
                VALIDATION_ERROR, f"Missing required target field: {field_name}"
            )

    t_type = str(raw["type"])
    if t_type not in {"asterisk", "freeswitch"}:
        raise ToolError(
            VALIDATION_ERROR, f"Invalid target type for {raw.get('id')}: {t_type}"
        )

    environment = str(raw.get("environment", "unknown")).strip().lower() or "unknown"
    allowed_envs = {"lab", "staging", "production", "prod", "unknown"}
    if environment not in allowed_envs:
        raise ToolError(
            VALIDATION_ERROR,
            f"Invalid target environment for {raw.get('id')}: {environment}",
            {"allowed": sorted(allowed_envs)},
        )
    safety_tier = str(raw.get("safety_tier", "standard")).strip().lower() or "standard"
    allowed_tiers = {"standard", "lab_safe", "restricted"}
    if safety_tier not in allowed_tiers:
        raise ToolError(
            VALIDATION_ERROR,
            f"Invalid target safety_tier for {raw.get('id')}: {safety_tier}",
            {"allowed": sorted(allowed_tiers)},
        )
    allow_active_validation_raw = raw.get("allow_active_validation", False)
    if not isinstance(allow_active_validation_raw, bool):
        raise ToolError(
            VALIDATION_ERROR,
            f"Field 'targets[{raw.get('id', '?')}].allow_active_validation' must be boolean",
        )

    ami = None
    if isinstance(raw.get("ami"), dict):
        ami_raw = raw["ami"]
        ami = AMIConfig(
            host=str(ami_raw.get("host", raw["host"])),
            port=int(ami_raw.get("port", 5038)),
            username_env=_require_env_name(
                ami_raw.get("username_env"),
                field_name=f"targets[{raw.get('id', '?')}].ami.username_env",
            ),
            password_env=_require_env_name(
                ami_raw.get("password_env"),
                field_name=f"targets[{raw.get('id', '?')}].ami.password_env",
            ),
        )

    ari = None
    if isinstance(raw.get("ari"), dict):
        ari_raw = raw["ari"]
        ari = ARIConfig(
            url=str(ari_raw.get("url", "")),
            username_env=_require_env_name(
                ari_raw.get("username_env"),
                field_name=f"targets[{raw.get('id', '?')}].ari.username_env",
            ),
            password_env=_require_env_name(
                ari_raw.get("password_env"),
                field_name=f"targets[{raw.get('id', '?')}].ari.password_env",
            ),
            app=str(ari_raw.get("app", "telecom_mcp")),
        )

    esl = None
    if isinstance(raw.get("esl"), dict):
        esl_raw = raw["esl"]
        esl = ESLConfig(
            host=str(esl_raw.get("host", raw["host"])),
            port=int(esl_raw.get("port", 8021)),
            password_env=_require_env_name(
                esl_raw.get("password_env"),
                field_name=f"targets[{raw.get('id', '?')}].esl.password_env",
            ),
        )

    logs = None
    if isinstance(raw.get("logs"), dict):
        logs_raw = raw["logs"]
        path = str(logs_raw.get("path", "")).strip()
        if not path:
            raise ToolError(
                VALIDATION_ERROR,
                f"Missing required field: targets[{raw.get('id', '?')}].logs.path",
            )
        source_command_raw = logs_raw.get("source_command")
        source_command = None
        if isinstance(source_command_raw, str):
            cleaned = source_command_raw.strip()
            source_command = cleaned or None
        logs = LogConfig(path=path, source_command=source_command)

    return TargetConfig(
        id=str(raw["id"]),
        type=t_type,
        host=str(raw["host"]),
        environment=environment,
        safety_tier=safety_tier,
        allow_active_validation=allow_active_validation_raw,
        ami=ami,
        ari=ari,
        esl=esl,
        logs=logs,
    )


def load_settings(
    targets_file: str | Path,
    *,
    mode: str | None = None,
    write_allowlist: list[str] | None = None,
    cooldown_seconds: int = 30,
    max_calls_per_window: int = 200,
    rate_limit_window_seconds: float = 1.0,
    tool_timeout_seconds: float = 5.0,
) -> Settings:
    path_obj = Path(targets_file)
    if not path_obj.exists():
        raise ToolError(VALIDATION_ERROR, f"Targets file not found: {path_obj}")

    raw = _parse_targets_yaml(path_obj)
    raw_targets = raw.get("targets")
    if not isinstance(raw_targets, list):
        raise ToolError(VALIDATION_ERROR, "targets.yaml field 'targets' must be a list")

    targets = [_as_target(item) for item in raw_targets]
    return Settings(
        targets=targets,
        mode=parse_mode(mode) if mode else Mode.INSPECT,
        write_allowlist=write_allowlist or [],
        cooldown_seconds=cooldown_seconds,
        max_calls_per_window=max_calls_per_window,
        rate_limit_window_seconds=rate_limit_window_seconds,
        tool_timeout_seconds=tool_timeout_seconds,
    )
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _require_env_name(raw_value: Any, *, field_name: str) -> str:
    value = str(raw_value or "").strip()
    if not value:
        raise ToolError(VALIDATION_ERROR, f"Missing required field: {field_name}")
    if not _ENV_NAME_RE.fullmatch(value):
        raise ToolError(
            VALIDATION_ERROR,
            f"Invalid environment variable name for {field_name}: {value}",
        )
    return value
