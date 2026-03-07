# Transport and Framing Fixes

## This Run
No additional transport/framing code changes.

## Current State
- Auth lifecycle and framed parser behavior are covered by connector tests.
- Malformed `Content-Length` rejection coverage exists.

## Evidence
- `tests/test_connectors.py` includes:
  - fragmented content-length reads
  - event interleaving
  - unexpected frame type rejection
  - malformed content-length rejection
