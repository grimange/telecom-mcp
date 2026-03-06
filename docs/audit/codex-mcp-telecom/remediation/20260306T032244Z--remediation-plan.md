# Remediation Plan (Normalized Findings)

## Decision table

| finding_id | source_file | defect_class | evidence | confidence | env_sensitivity | batch | eligibility | action |
|---|---|---|---|---|---|---|---|---|
| F-01 | root-cause-and-next-actions.md | DOC_DRIFT | modernization docs list Stage-10 fixture/state tools, runtime discovers 20 telecom/asterisk/freeswitch tools | HIGH | NONE | E | ELIGIBLE_FOR_REMEDIATION | Updated modernization MCP docs and top-level README tool/protocol guidance |
| F-02 | root-cause-and-next-actions.md | SANDBOX_OR_ENVIRONMENTAL | socket/DNS failures (`Operation not permitted`, name resolution failure) | HIGH | HIGH | N/A | DEFER_ENVIRONMENTAL_ONLY | No code changes; document environment prerequisite and defer out-of-sandbox validation |
| F-03 | root-cause-and-next-actions.md | EXTERNAL_DEPENDENCY_STARTUP_DEFECT (env-scoped) | system `pytest` path misses `anyio`; `.venv/bin/python -m pytest` succeeds | HIGH | MODERATE | A/E | CONFIG_ONLY | Added explicit `.venv` test invocation guidance in README |
| F-04 | root-cause-and-next-actions.md | RUNTIME_STATE_DEFECT (stdin-closed edge case) | `stdin=/dev/null` caused traceback during stdin pipe registration | MEDIUM | MODERATE | B | ELIGIBLE_FOR_REMEDIATION | Added clean guard + structured stderr warning; added regression test |
| F-05 | schema-and-contract.md | SCHEMA_CONTRACT_DEFECT | no deterministic schema defect confirmed | HIGH | LOW | D | DEFER_INSUFFICIENT_EVIDENCE | No schema changes |
| F-06 | tool-discovery.md | TOOL_REGISTRATION_DEFECT | none confirmed; declared and discovered match | HIGH | LOW | C | DEFER_INSUFFICIENT_EVIDENCE | No registration changes |

## Gating application
- Applied only F-01, F-03, F-04.
- Deferred F-02 because environmental-only.
- Deferred F-05/F-06 because no independent defect evidence.
