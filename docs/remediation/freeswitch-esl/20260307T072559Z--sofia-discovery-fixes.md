# Sofia Discovery Fixes

## Problem Addressed
Heuristic parser under-parsed real `sofia status` tabular output.

## Fix Implemented
- Extended `normalize/freeswitch.py::_parse_sofia_status_structured` to parse canonical tabular rows:
  - `profile` rows -> profile inventory with state.
  - `alias` rows -> alias map.
  - `gateway` rows -> gateway inventory with profile association (including `profile::gateway` naming).

## Regression Coverage
- Added `test_normalize_sofia_status_parses_tabular_sofia_output` in `tests/test_freeswitch_normalize.py`.

## Result
Profile/gateway completeness improved for canonical table-form outputs returned by live FreeSWITCH `sofia status`.
