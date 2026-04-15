# Transport and Framing Fixes

## New Fixes in This Run
- Added negative test coverage for malformed ESL frame headers:
  - `Content-Length: nope` now verified to raise `UPSTREAM_ERROR`.
  - Test: `tests/test_connectors.py::test_esl_api_rejects_malformed_content_length`.

## Existing Transport Controls (Verified)
- Auth-first handshake gate.
- Strict expected frame types (`api/response` for API path).
- Event-frame skip logic while awaiting command reply.
- Buffered multi-frame / partial-read parser.

## Status
- Framing hardening is now covered by positive + negative regression paths.
