from __future__ import annotations

from telecom_mcp.normalize import freeswitch as norm


def test_parse_channels_from_show_channels_csv() -> None:
    raw = (
        "Content-Type: api/response\n"
        "\n"
        "+OK uuid,direction,created,created_epoch,name,state,cid_name,cid_num,ip_addr,dest,"
        "presence_id,callstate,callee_name,callee_num,callee_direction\n"
        "1111,inbound,2026-03-06 10:00:00,0,sofia/internal/1001@pbx,CS_EXECUTE,Alice,1001,"
        "10.0.0.11,1002,,ACTIVE,Bob,1002,outbound\n"
        "1 total.\n"
    )
    parsed = norm.parse_channels(raw)
    assert len(parsed) == 1
    assert parsed[0]["uuid"] == "1111"
    assert parsed[0]["caller"] == "1001"
    assert parsed[0]["callee"] == "1002"
    assert parsed[0]["state"] == "ACTIVE"


def test_parse_calls_from_show_calls_csv() -> None:
    raw = (
        "+OK uuid,direction,created,created_epoch,name,state,cid_name,cid_num,ip_addr,dest,"
        "presence_id,callstate,callee_name,callee_num,callee_direction,call_uuid\n"
        "1111,inbound,2026-03-06 10:00:00,0,sofia/internal/1001@pbx,CS_EXECUTE,Alice,1001,"
        "10.0.0.11,1002,,ACTIVE,Bob,1002,outbound,call-abc\n"
        "1 total.\n"
    )
    parsed = norm.parse_calls(raw)
    assert len(parsed) == 1
    assert parsed[0]["call_id"] == "call-abc"
    assert parsed[0]["state"] == "ACTIVE"


def test_parse_registrations_from_sofia_status() -> None:
    raw = (
        "Registrations:\n"
        "1001 10.0.0.11 sip:1001@10.0.0.11:5060 REGED\n"
        "2001 10.0.0.12 sip:2001@10.0.0.12:5060 UNREGED\n"
    )
    parsed = norm.parse_registrations(raw)
    assert len(parsed) == 2
    assert parsed[0]["user"] == "1001"
    assert parsed[0]["status"] == "REGED"
    assert parsed[1]["status"] == "UNREGED"


def test_normalize_channels_includes_quality_when_unparsed() -> None:
    payload = norm.normalize_channels([], 50, "garbage")
    assert payload["data_quality"]["completeness"] == "partial"
    assert payload["channels"] == []
