# API Command Validation

## Commands Executed
1. `status` -> success (`c-697cee9402b1`)
2. `sofia status` -> success (`c-020132f39e92`)
3. `sofia status profile internal` -> success (`c-78983cc806a3`)
4. `sofia status profile external` -> success (`c-993fb679d8a4`)
5. `show channels` -> success, `0 total.` (`c-6c065e7d1781`)

## Result
Read-only API command path is functioning on real target.

## Observation
`freeswitch.version` in this runtime returned `version: unknown` while raw version text contains `1.10.11-release...` (`c-edd9ee3c63d1`), indicating version parsing/runtime drift in deployed server code.
