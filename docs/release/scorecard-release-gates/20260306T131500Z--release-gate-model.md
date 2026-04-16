# Release Gate Model

This model consumes:
- scorecard policy input (`score`, `confidence`, `freshness`, `policy_handoff.stop_conditions`, `recommended_escalations`)
- validation outcomes (`smoke_status`, `post_change_status`, `cleanup_ok`, `conflicting_evidence`)
- change context (`high_risk_change`)

Decision outputs:
- `allow`
- `hold`
- `escalate`

Design rules:
- low confidence never allows promotion
- stale evidence never allows promotion
- validation failures force hold
- explicit escalation signals force escalate
- high-risk changes require stronger score posture
