"""Configuration loading for telecom targets and runtime policy."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .authz import Mode, parse_mode
from .errors import AUTH_FAILED, NOT_FOUND, VALIDATION_ERROR, ToolError


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
class TargetConfig:
    id: str
    type: str
    host: str
    environment: str = "unknown"
    ami: AMIConfig | None = None
    ari: ARIConfig | None = None
    esl: ESLConfig | None = None


@dataclass(slots=True)
class Settings:
    targets: list[TargetConfig]
    mode: Mode = Mode.INSPECT
    write_allowlist: list[str] = field(default_factory=list)
    cooldown_seconds: int = 30
    max_calls_per_window: int = 200
    rate_limit_window_seconds: float = 1.0

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


def _parse_targets_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if not any(line.strip().startswith("targets:") for line in lines):
        raise ToolError(
            VALIDATION_ERROR, "targets.yaml must contain top-level 'targets:' key"
        )

    targets: list[dict[str, Any]] = []
    current_target: dict[str, Any] | None = None
    current_section: dict[str, Any] | None = None

    for raw in lines:
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue

        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)

        if stripped == "targets:":
            continue

        if stripped.startswith("- "):
            payload = stripped[2:]
            if not payload or ":" not in payload:
                raise ToolError(
                    VALIDATION_ERROR, f"Invalid list item in targets file: {raw}"
                )
            key, value = payload.split(":", 1)
            current_target = {key.strip(): _parse_scalar(value)}
            targets.append(current_target)
            current_section = None
            continue

        if current_target is None:
            continue

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

    return {"targets": targets}


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

    ami = None
    if isinstance(raw.get("ami"), dict):
        ami_raw = raw["ami"]
        ami = AMIConfig(
            host=str(ami_raw.get("host", raw["host"])),
            port=int(ami_raw.get("port", 5038)),
            username_env=str(ami_raw.get("username_env", "")),
            password_env=str(ami_raw.get("password_env", "")),
        )

    ari = None
    if isinstance(raw.get("ari"), dict):
        ari_raw = raw["ari"]
        ari = ARIConfig(
            url=str(ari_raw.get("url", "")),
            username_env=str(ari_raw.get("username_env", "")),
            password_env=str(ari_raw.get("password_env", "")),
            app=str(ari_raw.get("app", "telecom_mcp")),
        )

    esl = None
    if isinstance(raw.get("esl"), dict):
        esl_raw = raw["esl"]
        esl = ESLConfig(
            host=str(esl_raw.get("host", raw["host"])),
            port=int(esl_raw.get("port", 8021)),
            password_env=str(esl_raw.get("password_env", "")),
        )

    return TargetConfig(
        id=str(raw["id"]),
        type=t_type,
        host=str(raw["host"]),
        environment=str(raw.get("environment", "unknown")),
        ami=ami,
        ari=ari,
        esl=esl,
    )


def load_settings(
    targets_file: str | Path,
    *,
    mode: str | None = None,
    write_allowlist: list[str] | None = None,
    cooldown_seconds: int = 30,
    max_calls_per_window: int = 200,
    rate_limit_window_seconds: float = 1.0,
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
    )
