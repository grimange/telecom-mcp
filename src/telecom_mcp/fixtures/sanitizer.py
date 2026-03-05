"""Sanitization helpers for telecom fixture capture."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..errors import VALIDATION_ERROR, ToolError

SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "auth",
    "authuser",
    "sip_password",
    "ari_password",
    "ami_password",
    "esl_password",
}

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
PHONE_RE = re.compile(r"\b\+?\d{7,15}\b")
DOMAIN_RE = re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b")
SIP_URI_RE = re.compile(r"sip:([A-Za-z0-9_.-]+)@([A-Za-z0-9_.:-]+)", flags=re.IGNORECASE)
SECRET_VALUE_RE = re.compile(
    r"(?im)(\b(?:password|passwd|token|secret|authorization|authuser)\b\s*[:=]\s*)([^\r\n]+)"
)


@dataclass(slots=True)
class FixtureSanitizer:
    """Redacts secrets and sensitive telecom identifiers from fixture data."""

    _endpoint_map: dict[str, str] = field(default_factory=dict)
    _user_map: dict[str, str] = field(default_factory=dict)
    _host_map: dict[str, str] = field(default_factory=dict)
    _phone_map: dict[str, str] = field(default_factory=dict)
    _domain_map: dict[str, str] = field(default_factory=dict)

    @property
    def rule_count(self) -> int:
        return 5

    def sanitize_text(self, value: str) -> str:
        if not value:
            return value

        text = SECRET_VALUE_RE.sub(r"\1***REDACTED***", value)

        def _sip_replace(match: re.Match[str]) -> str:
            user = self._map_value(self._user_map, match.group(1), "user")
            host = self._map_value(self._host_map, match.group(2), "host")
            return f"sip:{user}@{host}"

        text = SIP_URI_RE.sub(_sip_replace, text)
        text = IPV4_RE.sub(lambda m: self._map_value(self._host_map, m.group(0), "host"), text)
        text = PHONE_RE.sub(
            lambda m: self._map_value(self._phone_map, m.group(0), "phone"), text
        )
        text = DOMAIN_RE.sub(
            lambda m: self._map_value(self._domain_map, m.group(0), "domain"), text
        )
        return text

    def sanitize_data(self, value: Any, *, key_hint: str = "") -> Any:
        if isinstance(value, Mapping):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                key_lower = str(key).lower()
                if key_lower in SENSITIVE_KEYS:
                    sanitized[key] = "***REDACTED***"
                elif key_lower in {"endpoint", "endpoint_id", "aor"} and isinstance(
                    item, str
                ):
                    sanitized[key] = self._map_value(
                        self._endpoint_map, item, "endpoint"
                    )
                elif key_lower in {"user", "username", "caller", "callee"} and isinstance(
                    item, str
                ):
                    sanitized[key] = self._map_value(self._user_map, item, "user")
                else:
                    sanitized[key] = self.sanitize_data(item, key_hint=key_lower)
            return sanitized

        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self.sanitize_data(item, key_hint=key_hint) for item in value]

        if isinstance(value, str):
            if key_hint in SENSITIVE_KEYS:
                return "***REDACTED***"
            return self.sanitize_text(value)

        return value

    def sanitize_json_text(self, raw_json: str) -> dict[str, Any] | list[Any]:
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ToolError(
                VALIDATION_ERROR,
                "Expected valid JSON payload while sanitizing fixture",
                {"reason": str(exc)},
            ) from exc
        return self.sanitize_data(parsed)

    def assert_no_sensitive_markers(self, value: Any) -> None:
        text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        if IPV4_RE.search(text):
            raise ToolError(VALIDATION_ERROR, "Sanitized fixture still includes IPv4")
        if PHONE_RE.search(text):
            raise ToolError(
                VALIDATION_ERROR, "Sanitized fixture still includes phone number"
            )

        lower = text.lower()
        for marker in ("password:", "token:", "authorization:", "authuser:"):
            if marker in lower and "***redacted***" not in lower:
                raise ToolError(
                    VALIDATION_ERROR,
                    "Sanitized fixture still includes credential marker",
                    {"marker": marker},
                )

    def _map_value(
        self, mapping: dict[str, str], original: str, label_prefix: str
    ) -> str:
        key = original.strip()
        if not key:
            return key
        if key not in mapping:
            mapping[key] = f"{label_prefix}-{chr(ord('A') + len(mapping))}"
        return mapping[key]
