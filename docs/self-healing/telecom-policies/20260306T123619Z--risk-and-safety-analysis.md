# Risk and Safety Analysis

## Recoverable Classes
- transient observability failures (safe retry)
- stale SIP visibility with approved bounded refresh/reload
- gateway/profile state staleness with approved refresh action
- post-change validation regressions in known safe buckets
- temporary drift in lab-safe environments

## Escalate-Only Classes
- high-risk ambiguous failures
- unsupported/unsafe routing or configuration mutations
- repeated failures beyond retry/cooldown boundaries

## Unsupported Classes
- arbitrary dialplan or endpoint reconfiguration
- bulk channel teardown
- unrestricted module mutation in shared production contexts

## Blast-Radius Boundaries
- explicit mode and target eligibility gates
- retry and cooldown guardrails
- escalation on low confidence/conflicting evidence
