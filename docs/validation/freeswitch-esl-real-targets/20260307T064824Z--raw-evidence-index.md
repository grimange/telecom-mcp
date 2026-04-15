# Raw Evidence Index

## Connectivity / Inventory
- `c-f6ac911fd0d9`: `telecom.list_targets` includes `fs-1`

## API Command Evidence
- `c-697cee9402b1`: `freeswitch.api status` (8 lines)
- `c-020132f39e92`: `freeswitch.api sofia status` (10 lines)
- `c-78983cc806a3`: `freeswitch.api sofia status profile internal` (36 lines)
- `c-993fb679d8a4`: `freeswitch.api sofia status profile external` (34 lines)
- `c-6c065e7d1781`: `freeswitch.api show channels` (`0 total.`)

## Tool-level Normalized Evidence
- `c-edd9ee3c63d1`: `freeswitch.version` raw contains full version string, parsed version returned `unknown`
- `c-d662eec12c13`: `freeswitch.sofia_status` parsed profiles/gateways
- `c-c3b4096ab423`: `freeswitch.channels` empty with partial data_quality

## Error Evidence
- `c-0ce9334915a8`: `bgapi status` -> `NOT_ALLOWED`
- `c-3f42a5c31b70`: `status foo` -> `NOT_ALLOWED`
- `c-433961005ca8`: invalid `uuid_dump` -> `NOT_FOUND`
- `c-ab090dfbc010`: invalid Sofia profile returns raw `Invalid Profile!` in partial data_quality response
- `c-07567a08050f`, `c-899ec50afd59`: `freeswitch.health` -> `UPSTREAM_ERROR(TypeError)`
- `c-04c0be001276`: `telecom.capture_snapshot` -> `TIMEOUT`

## Summary Evidence
- `c-51d44eaefdf6`: `telecom.summary(fs-1)` degraded due health collector failure
