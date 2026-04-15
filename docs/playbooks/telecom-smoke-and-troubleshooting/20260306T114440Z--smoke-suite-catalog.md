# Smoke Suite Catalog (Stage-02)

## 1) baseline_read_only_smoke
- Purpose: Verify safe baseline observability.
- Required checks:
  - health
  - summary
  - endpoints
  - registrations
  - channels
- Optional checks:
  - logs
  - inventory
- Pass/warn/fail criteria:
  - fail: required check failed
  - warn: only optional checks degraded
  - pass: all checks passed
- Runtime expectation: short bounded (<10 tool calls)
- Safety class: read-only

## 2) registration_visibility_smoke
- Purpose: Verify registration observability coherence.
- Required checks:
  - endpoints load
  - registrations load
  - count reconcile check
- Optional checks: none
- Pass/warn/fail criteria:
  - fail: required load failed
  - warn: reconcile anomaly
  - pass: loads + reconcile pass
- Runtime expectation: short bounded
- Safety class: read-only

## 3) call_state_visibility_smoke
- Purpose: Verify channel/call observability.
- Required checks:
  - channels query
  - detail query for available channel or graceful none
- Optional checks:
  - bridges (Asterisk)
  - calls (FreeSWITCH)
- Pass/warn/fail criteria:
  - fail: channels query failed
  - warn: optional checks degrade
  - pass: required checks pass
- Runtime expectation: short bounded
- Safety class: read-only

## 4) audit_baseline_smoke
- Purpose: Verify baseline audit evidence generation.
- Required checks:
  - version
  - inventory
- Optional checks:
  - modules
  - compare helper (when `params.compare_with` provided)
- Pass/warn/fail criteria:
  - fail: required checks failed
  - warn: optional checks degraded/skipped
  - pass: required checks pass
- Runtime expectation: short bounded
- Safety class: read-only

## 5) active_validation_smoke (optional)
- Purpose: gated active validation.
- Required checks:
  - registration probe
- Optional checks:
  - cleanup verification
- Pass/warn/fail criteria:
  - blocked in inspect/plan
  - requires active-probe enablement
- Runtime expectation: short bounded
- Safety class: gated-write
