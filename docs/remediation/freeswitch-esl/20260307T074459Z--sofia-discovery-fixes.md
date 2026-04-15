# Sofia Discovery Fixes

## This Run
No new Sofia parser code changes.

## Current State
- Repository parser includes table-row handling for profile/alias/gateway.
- Regression coverage for tabular `sofia status` exists in `tests/test_freeswitch_normalize.py`.

## Remaining Gap
Live runtime still appears to under-parse Sofia output, suggesting deployment/version skew rather than unresolved repo logic.
