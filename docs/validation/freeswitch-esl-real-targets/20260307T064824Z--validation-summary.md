# FreeSWITCH ESL Real-Target Validation Summary

## Run Metadata
- Date (UTC): 2026-03-07
- Target: `fs-1` (`38.107.174.40:8021`)
- Inputs: `targets.yaml`, `docs/remediation/freeswitch-esl/20260307T064415Z--*`

## Verdict
Partial pass.

## Passed Areas
- Real target reachability and authenticated command execution for read-only API paths (`status`, `sofia status`, `sofia status profile internal|external`, `show channels`).
- Safe error classification for some command/resource cases:
  - invalid allowlist command -> `NOT_ALLOWED`
  - missing channel UUID -> `NOT_FOUND`

## Failed / Degraded Areas
- `freeswitch.health` fails on real target with `UPSTREAM_ERROR` (`TypeError`) in this runtime.
- `telecom.summary(fs-1)` is degraded because internal `freeswitch.health` fails.
- `telecom.capture_snapshot(fs-1)` timed out at runtime default timeout (5s).
- `bgapi status` validation cannot be executed in current v1 runtime because `bgapi` is intentionally blocked by API allowlist.

## Confidence
- Transport/API command path: High
- Health contract correctness on real target: Low (failing)
- Sofia discovery correctness: Moderate
- Error taxonomy completeness: Moderate (auth-fail / parse-fail / forced connection-fail not directly exercised)
