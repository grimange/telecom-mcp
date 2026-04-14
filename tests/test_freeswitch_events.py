from __future__ import annotations

from telecom_mcp.config import ESLConfig
from telecom_mcp.freeswitch_events import (
    FreeSWITCHEventMonitor,
    normalize_event_frame,
)


def test_event_monitor_snapshot_empty_is_valid() -> None:
    monitor = FreeSWITCHEventMonitor(
        pbx_id="fs-1",
        config=ESLConfig(host="127.0.0.1", port=8021, password_env="FS_PASS"),
        connector_factory=lambda *_args, **_kwargs: None,
    )
    monitor._state = "available"
    monitor._monitor_started_at = "2026-04-14T00:00:00Z"
    monitor._last_healthy_at = "2026-04-14T00:00:00Z"
    snapshot = monitor.snapshot(limit=10, event_names=None, event_family=None, include_raw=False)
    assert snapshot["events"] == []
    assert snapshot["buffered_events"] == 0
    assert snapshot["overflowed"] is False
    assert snapshot["freshness"]["monitor_state"] == "available"


def test_event_monitor_filters_and_raw_projection() -> None:
    monitor = FreeSWITCHEventMonitor(
        pbx_id="fs-1",
        config=ESLConfig(host="127.0.0.1", port=8021, password_env="FS_PASS"),
        connector_factory=lambda *_args, **_kwargs: None,
    )
    monitor.ingest_event(
        normalize_event_frame(
            target_id="fs-1",
            session_id="sess-1",
            observed_at="2026-04-14T00:00:00Z",
            content_type="text/event-plain",
            headers={"Event-Name": "CHANNEL_CREATE", "Unique-Id": "uuid-1"},
            body="Event-Name: CHANNEL_CREATE\nUnique-Id: uuid-1",
        )
    )
    monitor.ingest_event(
        normalize_event_frame(
            target_id="fs-1",
            session_id="sess-1",
            observed_at="2026-04-14T00:00:01Z",
            content_type="text/event-plain",
            headers={"Event-Name": "HEARTBEAT", "Core-UUID": "core-1"},
            body="Event-Name: HEARTBEAT\nCore-UUID: core-1",
        )
    )

    snapshot = monitor.snapshot(
        limit=10,
        event_names={"CHANNEL_CREATE"},
        event_family="channel",
        include_raw=True,
    )
    assert len(snapshot["events"]) == 1
    assert snapshot["events"][0]["event_name"] == "CHANNEL_CREATE"
    assert snapshot["events"][0]["event_family"] == "channel"
    assert snapshot["events"][0]["identifiers"]["unique_id"] == "uuid-1"
    assert "raw" in snapshot["events"][0]


def test_normalize_event_frame_derives_event_name_from_body_headers() -> None:
    event = normalize_event_frame(
        target_id="fs-1",
        session_id="sess-1",
        observed_at="2026-04-14T00:00:00Z",
        content_type="text/event-plain",
        headers={},
        body="Event-Name: HEARTBEAT\nCore-UUID: core-1\n",
    )
    assert event.event_name == "HEARTBEAT"
    assert event.event_family == "system"
    assert event.identifiers["core_uuid"] == "core-1"


def test_event_monitor_tracks_overflow() -> None:
    monitor = FreeSWITCHEventMonitor(
        pbx_id="fs-1",
        config=ESLConfig(host="127.0.0.1", port=8021, password_env="FS_PASS"),
        connector_factory=lambda *_args, **_kwargs: None,
        buffer_capacity=2,
    )
    for idx in range(3):
        monitor.ingest_event(
            normalize_event_frame(
                target_id="fs-1",
                session_id="sess-1",
                observed_at=f"2026-04-14T00:00:0{idx}Z",
                content_type="text/event-plain",
                headers={"Event-Name": f"CHANNEL_{idx}", "Unique-Id": f"uuid-{idx}"},
                body=f"Event-Name: CHANNEL_{idx}\nUnique-Id: uuid-{idx}",
            )
        )

    snapshot = monitor.snapshot(limit=10, event_names=None, event_family=None, include_raw=False)
    assert snapshot["buffered_events"] == 2
    assert snapshot["dropped_events"] == 1
    assert snapshot["overflowed"] is True


def test_event_monitor_filter_matches_unfiltered_truth() -> None:
    monitor = FreeSWITCHEventMonitor(
        pbx_id="fs-1",
        config=ESLConfig(host="127.0.0.1", port=8021, password_env="FS_PASS"),
        connector_factory=lambda *_args, **_kwargs: None,
    )
    monitor.ingest_event(
        normalize_event_frame(
            target_id="fs-1",
            session_id="sess-1",
            observed_at="2026-04-14T00:00:00Z",
            content_type="text/event-plain",
            headers={},
            body="Event-Name: HEARTBEAT\nCore-UUID: core-1\n",
        )
    )
    unfiltered = monitor.snapshot(limit=10, event_names=None, event_family=None, include_raw=True)
    filtered = monitor.snapshot(limit=10, event_names={"HEARTBEAT"}, event_family=None, include_raw=False)
    assert unfiltered["events"][0]["event_name"] == "HEARTBEAT"
    assert filtered["events"][0]["event_name"] == "HEARTBEAT"


def test_event_monitor_marks_stale_when_last_event_is_old(monkeypatch) -> None:
    monitor = FreeSWITCHEventMonitor(
        pbx_id="fs-1",
        config=ESLConfig(host="127.0.0.1", port=8021, password_env="FS_PASS"),
        connector_factory=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr("telecom_mcp.freeswitch_events._now_epoch_ms", lambda: 1_000_000)
    monitor._monitor_started_at = "1970-01-01T00:16:20Z"
    monitor._last_healthy_at = "1970-01-01T00:16:20Z"
    monitor._last_event_at = "1970-01-01T00:15:00Z"
    monitor._state = "available"

    snapshot = monitor.snapshot(limit=10, event_names=None, event_family=None, include_raw=False)
    assert snapshot["freshness"]["is_stale"] is True
    assert snapshot["freshness"]["staleness_reason"] == "event_stream_idle"
