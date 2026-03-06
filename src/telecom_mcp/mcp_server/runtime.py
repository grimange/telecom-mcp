"""Runtime flags and shared helpers for MCP SDK server mode."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class RuntimeFlags:
    fixtures: bool
    real_pbx: bool
    transport: str
    strict_startup: bool
    require_explicit_targets_file: bool
    require_confirm_token: bool

    def as_mode_dict(self) -> dict[str, bool | str]:
        return asdict(self)


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip() == "1"


def load_runtime_flags() -> RuntimeFlags:
    transport = os.getenv("TELECOM_MCP_TRANSPORT", "stdio").strip().lower()
    if transport not in {"stdio", "http"}:
        transport = "stdio"

    return RuntimeFlags(
        fixtures=_env_bool("TELECOM_MCP_FIXTURES", default=True),
        real_pbx=_env_bool("TELECOM_MCP_ENABLE_REAL_PBX", default=False),
        transport=transport,
        strict_startup=_env_bool("TELECOM_MCP_STRICT_STARTUP", default=False),
        require_explicit_targets_file=_env_bool(
            "TELECOM_MCP_REQUIRE_TARGETS_FILE_EXPLICIT", default=False
        ),
        require_confirm_token=_env_bool("TELECOM_MCP_REQUIRE_CONFIRM_TOKEN", default=False),
    )


def iso8601_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
