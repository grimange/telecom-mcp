# Sofia Discovery Fixes

## Implemented
- Health flow now validates `status` and `version` responses before Sofia discovery fallback logic.
- Existing fallback sequence retained:
  1. `sofia status`
  2. `sofia status profile internal`
  3. `sofia status profile external`

## Impact
- Prevents upstream invalid read payloads from being masked by later Sofia parsing failures.
- Improves error fidelity when control/auth payloads are returned unexpectedly.

## Files
- `src/telecom_mcp/tools/freeswitch.py`
