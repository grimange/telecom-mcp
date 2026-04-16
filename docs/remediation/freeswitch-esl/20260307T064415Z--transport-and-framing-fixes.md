# Transport and Framing Fixes

## Implemented
- Connector now requires `auth/request` greeting before auth command.
- Auth phase requires `command/reply` and `+OK` semantic acceptance.
- API phase requires `api/response`; non-event, non-expected frames now fail closed.
- Interleaved `text/event-*` frames are ignored while waiting for command response.
- Internal read buffer preserves multi-frame reads across socket chunks.
- Socket timeout call is guarded (`hasattr(sock, "settimeout")`) for mock compatibility.

## Key Files
- `src/telecom_mcp/connectors/freeswitch_esl.py`
- `tests/test_connectors.py`

## Regression Coverage Added/Updated
- Fragmented `Content-Length` API response with prior auth lifecycle.
- Interleaved event + API response in a single read.
- Rejection of unexpected `command/reply` during API response wait.
- Retry behavior after transient send error across reconnect.
