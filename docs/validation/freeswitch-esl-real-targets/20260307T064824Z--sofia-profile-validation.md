# Sofia Profile Validation

## Direct Checks
- `freeswitch.api sofia status` (`c-020132f39e92`) returned 4 profiles + 1 alias.
- `freeswitch.api sofia status profile internal` (`c-78983cc806a3`) returned detailed internal profile fields.
- `freeswitch.api sofia status profile external` (`c-993fb679d8a4`) returned detailed external profile fields.

## Adapter Output
- `freeswitch.sofia_status` (`c-d662eec12c13`) parsed:
  - `profiles`: 1
  - `gateways`: 1

## Gap
Raw output lists more profile rows than parsed output, so parser completeness remains partial despite non-empty results.

## Error Case
- `freeswitch.sofia_status(profile=definitely-missing-profile)` (`c-ab090dfbc010`) returned raw `Invalid Profile!` and empty parsed lists with partial data_quality.
- This is graceful but should ideally map to a structured `NOT_FOUND` error in stricter contracts.
