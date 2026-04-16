# Decision Flow and Gating

## Flow
1. Load scorecard (`telecom.scorecard_target|cluster|environment` or explicit scorecard input).
2. Evaluate confidence and freshness.
3. Derive structured scorecard policy input.
4. Generate no-act/escalation/candidate recommendations.
5. Build handoff payload with stop conditions and suppressed policies.
6. Run self-healing eligibility evaluation.
7. Apply normal self-healing gating (mode, risk class, target safety, cooldown/retry).
8. Return evaluation-only, no-act/escalate, or eligible low-risk policy set.

## No-Bypass Guarantees
- No direct remediation execution from scorecard policy input generation.
- No cooldown override.
- No denylist/production safety override.
- No suppression of conflicting evidence.

## Stop Conditions
- `stale_score_with_no_refresh`
- `confidence_below_threshold`
- conflicting evidence suppression via `conflicting_evidence_no_action`

## Evidence and Explainability
Self-healing evaluation now includes:
- recommended candidates
- no-act candidates
- escalation recommendations
- required prechecks/evidence refresh
- policy handoff stop conditions and suppressed policy reasons
