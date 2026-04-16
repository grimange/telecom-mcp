# Migration and Refactor Batches

Run timestamp (UTC): `20260306T161805Z`

## Batch 1 — Highest-Leverage Safety Unification
- Workstreams: A, B, C.
- Files touched:
  - `src/telecom_mcp/safety/policy.py` (new)
  - `src/telecom_mcp/safety/__init__.py` (new)
  - `src/telecom_mcp/tools/telecom.py`
  - `src/telecom_mcp/tools/asterisk.py`
  - `src/telecom_mcp/tools/freeswitch.py`
- Local code migrated:
  - duplicated target eligibility checks
  - duplicated probe destination validation
- Tests added/moved:
  - `tests/test_safety_policy.py`
- Compatibility risks:
  - low (same denial semantics).
- Rollback plan:
  - revert shared module usage and restore local helpers in each tool module.

## Batch 2 — Active-System Stability Unification
- Workstreams: E.
- Files touched:
  - `src/telecom_mcp/execution/active_control.py` (new)
  - `src/telecom_mcp/execution/__init__.py` (new)
  - `src/telecom_mcp/tools/telecom.py`
  - `src/telecom_mcp/tools/asterisk.py`
  - `src/telecom_mcp/tools/freeswitch.py`
- Local code migrated:
  - ad-hoc absence of active concurrency controls replaced by shared guard.
- Tests added/moved:
  - additional concurrency tests in `tests/test_expansion_batch4_tools.py`.
- Compatibility risks:
  - medium (intentional `NOT_ALLOWED` under saturation).
- Rollback plan:
  - bypass guard usage in affected tool paths while retaining module.

## Batch 3 — Governance and Evidence Unification (Docs + Tests in this run)
- Workstreams: H (partial), F documentation alignment.
- Files touched:
  - `README.md`
  - `docs/security.md`
  - `docs/runbook.md`
  - `docs/telecom-mcp-implementation-plan.md`
  - `CHANGELOG.md`
- Local code migrated:
  - documentation now points to shared control-plane modules and active concurrency env controls.
- Tests added/moved:
  - recurrence-prevention tests and full regression rerun evidence.
- Compatibility risks:
  - low.
- Rollback plan:
  - revert docs/changelog changes only.

## Batch 4 — Local Logic Removal and Simplification
- Completed in this run for duplicated safety validators and eligibility checks.
- Deferred follow-on simplifications:
  - shared rollback/cleanup contract abstraction
  - shared confidence/freshness suppression contract abstraction
