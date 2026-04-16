"""Bounded passive FreeSWITCH event capture for inspect-mode readback."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
import threading
import time
import uuid
from typing import Any, Callable

from .config import ESLConfig
from .errors import AUTH_FAILED, CONNECTION_FAILED, ToolError

_DEFAULT_BUFFER_CAPACITY = 128
_DEFAULT_RETURN_LIMIT = 50
_DEFAULT_RAW_PREVIEW_CHARS = 2048
_MONITOR_TIMEOUT_S = 1.0
_POLL_INTERVAL_S = 0.25
_RESTART_DELAY_S = 0.2
_STALE_AFTER_MS = 60_000


def max_event_buffer_capacity() -> int:
    return _DEFAULT_BUFFER_CAPACITY


def max_recent_events_return_limit() -> int:
    return _DEFAULT_RETURN_LIMIT


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _now_epoch_ms() -> int:
    return int(time.time() * 1000)


def _parse_iso_to_epoch_ms(value: str | None) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed.timestamp() * 1000)


def _build_freshness(*, monitor_state: str, monitor_started_at: str | None, last_event_at: str | None, last_healthy_at: str | None) -> dict[str, Any]:
    now_ms = _now_epoch_ms()
    started_ms = _parse_iso_to_epoch_ms(monitor_started_at)
    event_ms = _parse_iso_to_epoch_ms(last_event_at)
    healthy_ms = _parse_iso_to_epoch_ms(last_healthy_at)

    reference_ms = event_ms if event_ms is not None else healthy_ms
    idle_duration_ms = None if reference_ms is None else max(now_ms - reference_ms, 0)
    since_start_ms = None if started_ms is None else max(now_ms - started_ms, 0)

    is_stale = False
    staleness_reason = None
    if monitor_state == "unavailable":
        is_stale = True
        staleness_reason = "monitor_unavailable"
    elif monitor_state == "degraded":
        is_stale = True
        staleness_reason = "monitor_degraded"
    elif idle_duration_ms is not None and idle_duration_ms > _STALE_AFTER_MS:
        is_stale = True
        staleness_reason = "event_stream_idle"

    return {
        "monitor_started_at": monitor_started_at,
        "last_event_at": last_event_at,
        "last_healthy_at": last_healthy_at,
        "idle_duration_ms": idle_duration_ms,
        "monitor_age_ms": since_start_ms,
        "is_stale": is_stale,
        "staleness_reason": staleness_reason,
        "stale_after_ms": _STALE_AFTER_MS,
        "monitor_state": monitor_state,
    }


@dataclass(slots=True)
class CapturedFreeSWITCHEvent:
    observed_at: str
    event_name: str
    event_family: str
    identifiers: dict[str, str]
    content_type: str
    session_id: str
    target_id: str
    raw: dict[str, Any]

    def to_public(self, *, include_raw: bool) -> dict[str, Any]:
        payload = {
            "observed_at": self.observed_at,
            "event_name": self.event_name,
            "event_family": self.event_family,
            "identifiers": dict(self.identifiers),
            "content_type": self.content_type,
            "session_id": self.session_id,
            "target_id": self.target_id,
        }
        if include_raw:
            payload["raw"] = dict(self.raw)
        return payload


def _truncate_text(value: str, *, max_chars: int = _DEFAULT_RAW_PREVIEW_CHARS) -> tuple[str, bool]:
    if len(value) <= max_chars:
        return value, False
    return value[:max_chars], True


def _normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    return {str(key).strip().lower(): str(value).strip() for key, value in headers.items()}


def _parse_header_lines(raw_text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in raw_text.replace("\r", "").splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key and value and key not in parsed:
            parsed[key] = value
    return parsed


def _derive_event_family(headers: dict[str, str]) -> str:
    subclass = str(headers.get("event-subclass", "")).strip()
    if "::" in subclass:
        return subclass.split("::", 1)[0].strip().lower() or "custom"
    event_name = str(headers.get("event-name", "")).strip().upper()
    if event_name.startswith("CHANNEL_"):
        return "channel"
    if event_name.startswith("CALL_"):
        return "call"
    if event_name.startswith("SOFIA_"):
        return "sofia"
    if event_name.startswith("RE_") or event_name in {"HEARTBEAT", "BACKGROUND_JOB", "SHUTDOWN"}:
        return "system"
    if event_name.startswith("CUSTOM"):
        return "custom"
    if event_name.startswith("MODULE_"):
        return "module"
    if event_name in {"HEARTBEAT", "BACKGROUND_JOB", "SHUTDOWN"}:
        return "system"
    if event_name == "CUSTOM":
        return "custom"
    if event_name:
        return "generic"
    return "unknown"


def _extract_identifiers(headers: dict[str, str]) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    for source_key, public_key in (
        ("unique-id", "unique_id"),
        ("channel-call-uuid", "channel_call_uuid"),
        ("channel-state", "channel_state"),
        ("caller-destination-number", "destination"),
        ("caller-caller-id-number", "caller"),
        ("variable_sip_call_id", "sip_call_id"),
        ("core-uuid", "core_uuid"),
    ):
        value = str(headers.get(source_key, "")).strip()
        if value:
            identifiers[public_key] = value
    return identifiers


def normalize_event_frame(
    *,
    target_id: str,
    session_id: str,
    observed_at: str,
    content_type: str,
    headers: dict[str, str],
    body: str,
) -> CapturedFreeSWITCHEvent:
    normalized_headers = _normalize_headers(headers)
    body_headers = _parse_header_lines(body)
    merged_headers = dict(body_headers)
    merged_headers.update(normalized_headers)
    event_name = (
        str(normalized_headers.get("event-name", "")).strip()
        or str(body_headers.get("event-name", "")).strip()
        or "unknown"
    )
    body_preview, body_truncated = _truncate_text(body)
    return CapturedFreeSWITCHEvent(
        observed_at=observed_at,
        event_name=event_name,
        event_family=_derive_event_family(merged_headers),
        identifiers=_extract_identifiers(merged_headers),
        content_type=content_type,
        session_id=session_id,
        target_id=target_id,
        raw={
            "headers": merged_headers,
            "body": body_preview,
            "body_truncated": body_truncated,
        },
    )


class FreeSWITCHEventMonitor:
    def __init__(
        self,
        *,
        pbx_id: str,
        config: ESLConfig,
        connector_factory: Callable[..., Any],
        buffer_capacity: int = _DEFAULT_BUFFER_CAPACITY,
    ) -> None:
        self.pbx_id = pbx_id
        self.config = config
        self.connector_factory = connector_factory
        self.buffer_capacity = min(max(buffer_capacity, 1), _DEFAULT_BUFFER_CAPACITY)
        self._buffer: deque[CapturedFreeSWITCHEvent] = deque(maxlen=self.buffer_capacity)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._started = False
        self._dropped_events = 0
        self._state = "unavailable"
        self._last_error: dict[str, Any] | None = None
        self._last_event_at: str | None = None
        self._monitor_started_at: str | None = None
        self._last_healthy_at: str | None = None
        self._session_id: str | None = None
        self._ever_healthy = False
        self._subscription_reply: str | None = None

    def ensure_started(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._state = "starting"
            self._monitor_started_at = _utc_now_iso()
            self._thread = threading.Thread(
                target=self._run,
                name=f"telecom-mcp-fs-events-{self.pbx_id}",
                daemon=True,
            )
            self._thread.start()

    def status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            state = self._state
            last_error = dict(self._last_error) if isinstance(self._last_error, dict) else None
            freshness = _build_freshness(
                monitor_state=state,
                monitor_started_at=self._monitor_started_at,
                last_event_at=self._last_event_at,
                last_healthy_at=self._last_healthy_at,
            )
            return {
                "supported": True,
                "state": state,
                "available": state == "available",
                "degraded": state == "degraded",
                "healthy": state == "available",
                "buffer_capacity": self.buffer_capacity,
                "buffered_events": len(self._buffer),
                "dropped_events": self._dropped_events,
                "last_event_at": self._last_event_at,
                "monitor_started_at": self._monitor_started_at,
                "last_healthy_at": self._last_healthy_at,
                "last_error": last_error,
                "session_id": self._session_id,
                "subscription_reply": self._subscription_reply,
                "freshness": freshness,
            }

    def snapshot(
        self,
        *,
        limit: int,
        event_names: set[str] | None = None,
        event_family: str | None = None,
        include_raw: bool,
    ) -> dict[str, Any]:
        capped_limit = min(max(limit, 1), _DEFAULT_RETURN_LIMIT)
        normalized_names = {item.strip().lower() for item in (event_names or set()) if item.strip()}
        family_filter = event_family.strip().lower() if isinstance(event_family, str) and event_family.strip() else None
        with self._lock:
            filtered: list[CapturedFreeSWITCHEvent] = []
            for event in reversed(self._buffer):
                if normalized_names and event.event_name.lower() not in normalized_names:
                    continue
                if family_filter and event.event_family.lower() != family_filter:
                    continue
                filtered.append(event)
                if len(filtered) >= capped_limit:
                    break
            filtered.reverse()
            freshness = _build_freshness(
                monitor_state=self._state,
                monitor_started_at=self._monitor_started_at,
                last_event_at=self._last_event_at,
                last_healthy_at=self._last_healthy_at,
            )
            return {
                "state": self._state,
                "healthy": self._state == "available",
                "events": [item.to_public(include_raw=include_raw) for item in filtered],
                "buffer_capacity": self.buffer_capacity,
                "buffered_events": len(self._buffer),
                "dropped_events": self._dropped_events,
                "overflowed": self._dropped_events > 0,
                "last_event_at": self._last_event_at,
                "monitor_started_at": self._monitor_started_at,
                "last_healthy_at": self._last_healthy_at,
                "last_error": dict(self._last_error) if isinstance(self._last_error, dict) else None,
                "session_id": self._session_id,
                "freshness": freshness,
            }

    def ingest_event(self, event: CapturedFreeSWITCHEvent) -> None:
        with self._lock:
            if len(self._buffer) >= self.buffer_capacity:
                self._dropped_events += 1
            self._buffer.append(event)
            self._last_event_at = event.observed_at
            self._last_healthy_at = event.observed_at

    def _set_state(self, state: str, *, error: dict[str, Any] | None = None, session_id: str | None = None) -> None:
        with self._lock:
            self._state = state
            self._last_error = error
            if session_id is not None:
                self._session_id = session_id
            if state == "available":
                self._last_healthy_at = _utc_now_iso()

    def _run(self) -> None:
        while not self._stop.is_set():
            connector = self.connector_factory(self.config, timeout_s=_MONITOR_TIMEOUT_S)
            session_id = f"fs-events-{self.pbx_id}-{uuid.uuid4().hex[:8]}"
            try:
                connector.connect()
                reply = connector.subscribe_events("plain")
                self._ever_healthy = True
                with self._lock:
                    self._state = "available"
                    self._last_error = None
                    self._session_id = session_id
                    self._subscription_reply = reply
                    self._last_healthy_at = _utc_now_iso()
                while not self._stop.is_set():
                    event_frame = connector.read_event(timeout_s=_POLL_INTERVAL_S)
                    if event_frame is None:
                        continue
                    self.ingest_event(
                        normalize_event_frame(
                            target_id=self.pbx_id,
                            session_id=session_id,
                            observed_at=_utc_now_iso(),
                            content_type=str(event_frame.get("content_type", "")),
                            headers=dict(event_frame.get("headers", {})),
                            body=str(event_frame.get("body", "")),
                        )
                    )
            except ToolError as exc:
                state = "degraded" if self._ever_healthy else "unavailable"
                if exc.code == AUTH_FAILED:
                    state = "unavailable"
                self._set_state(
                    state,
                    error={
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details or {},
                    },
                    session_id=session_id,
                )
            except Exception as exc:
                self._set_state(
                    "degraded" if self._ever_healthy else "unavailable",
                    error={
                        "code": CONNECTION_FAILED,
                        "message": "Passive FreeSWITCH event monitor failed",
                        "details": {"type": type(exc).__name__},
                    },
                    session_id=session_id,
                )
            finally:
                try:
                    connector.close()
                except Exception:
                    pass
            if self._stop.wait(_RESTART_DELAY_S):
                break


class NullFreeSWITCHEventMonitor:
    def ensure_started(self) -> None:
        return None

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "supported": True,
            "state": "unavailable",
            "available": False,
            "degraded": False,
            "healthy": False,
            "buffer_capacity": max_event_buffer_capacity(),
            "buffered_events": 0,
            "dropped_events": 0,
            "last_event_at": None,
            "monitor_started_at": None,
            "last_healthy_at": None,
            "last_error": {
                "code": AUTH_FAILED,
                "message": "Passive FreeSWITCH event monitor not configured",
                "details": {},
            },
            "session_id": None,
            "subscription_reply": None,
            "freshness": _build_freshness(
                monitor_state="unavailable",
                monitor_started_at=None,
                last_event_at=None,
                last_healthy_at=None,
            ),
        }

    def snapshot(
        self,
        *,
        limit: int,
        event_names: set[str] | None = None,
        event_family: str | None = None,
        include_raw: bool,
    ) -> dict[str, Any]:
        _ = limit, event_names, event_family, include_raw
        status = self.status_snapshot()
        return {
            "state": status["state"],
            "healthy": False,
            "events": [],
            "buffer_capacity": status["buffer_capacity"],
            "buffered_events": 0,
            "dropped_events": 0,
            "overflowed": False,
            "last_event_at": None,
            "monitor_started_at": None,
            "last_healthy_at": None,
            "last_error": status["last_error"],
            "session_id": None,
            "freshness": status["freshness"],
        }
