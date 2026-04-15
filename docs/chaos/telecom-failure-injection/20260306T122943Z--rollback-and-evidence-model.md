# Rollback and Evidence Model

## Before Injection
- run baseline smoke suite
- capture pre-chaos snapshot

## Detection During/After Injection
- run expected playbooks
- run expected smoke suites
- run audit checks
- record detection output in structured `evidence.detections`

## Rollback
- verify cleanup via cleanup checker
- classify rollback pass/warn outcome

## Post-Rollback Verification
- rerun baseline smoke
- verify postcheck results and include in evidence

## Evidence Guarantees
- phased status trace
- pre/post baseline checks
- detection references
- rollback verification data
