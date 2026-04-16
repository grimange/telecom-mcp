# Batch 3 Promotion Model

New tools:
- `telecom.release_promotion_decision`
- `telecom.release_gate_history`

Promotion decision aggregation:
- if any member decision is `escalate` => environment decision `escalate`
- else if any member decision is `hold` => environment decision `hold`
- else => `allow`

Outputs include member decisions and aggregated reasons.
