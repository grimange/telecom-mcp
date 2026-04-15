# Raw Evidence Index

## Inventory
- `c-c11e3604a331` -> `telecom.list_targets`

## API Responses
- `c-4cbac0983413` -> `freeswitch.api status`
- `c-3a5527d65fc9` -> `freeswitch.api sofia status`
- `c-77b4e6f36a4c` -> `freeswitch.api sofia status profile internal`
- `c-7e46b5388415` -> `freeswitch.api sofia status profile external`
- `c-f9868792bd3e` -> `freeswitch.api show channels`

## Tool-Level Parsed Outputs
- `c-1f860cc483f4` -> `freeswitch.version` (raw has version, parsed unknown)
- `c-5d5dbb41a505` -> `freeswitch.sofia_status` (subset parsing)
- `c-76d1bd520777` -> `freeswitch.channels`

## Errors
- `c-661416c02659` -> `bgapi status` blocked (`NOT_ALLOWED`)
- `c-eb0677ff0bc6` -> `status foo` blocked (`NOT_ALLOWED`)
- `c-b32355bd033c` -> missing UUID (`NOT_FOUND`)
- `c-7ca4e51dd956` -> invalid Sofia profile raw payload
- `c-f54a586af47f` -> health `UPSTREAM_ERROR` / `TypeError`

## Aggregated Checks
- `c-608796099661` -> `telecom.summary(fs-1)` degraded
- `c-b50f27bf6a46` -> `telecom.capture_snapshot(fs-1)` success
