# Open Risks and Follow-Ups

## Open Risks
1. Runtime deployment drift may still cause health/version behavior mismatch even when repository tests pass.
2. BGAPI contract validation remains unsupported by current read-only allowlist policy.
3. Additional malformed-frame variants (beyond non-integer content-length) are not yet covered.

## Follow-Ups
1. Redeploy runtime from current repository head and rerun `docs/prompts/freeswitch/03-esl-validation.md`.
2. If BGAPI support is required, implement a gated validation-only path and corresponding tests.
3. Add more parser-failure regression tests (truncated headers, duplicated conflicting headers, oversized malformed lengths).
