# Confidence and Freshness Rules

## Confidence Rules
- `low` or `unknown` confidence blocks action-oriented recommendations.
- `medium` confidence allows low-risk policy evaluation recommendations only.
- `high` confidence allows prioritized low-risk/lab-only evaluation recommendations.
- Unknown confidence always produces no-act/evidence-refresh stop conditions.

## Freshness Rules
- Freshness is derived from scorecard `generated_at`.
- `fresh`: within threshold.
- `stale`/`unknown`: blocks action-oriented recommendation handoff.
- Stale/unknown freshness requires evidence refresh before policy evaluation.

## Interaction Rules
- low score + low confidence => evidence refresh/no-act/escalation.
- low score + high confidence + non-critical integrity => low-risk lab evaluation candidates allowed.
- strong total score + degraded dimension => dimension-specific recommendations still allowed.
- acceptable score + incident burden weakness => escalation recommendation allowed.

## Current Thresholds
- stale threshold: 2 hours from `generated_at`.
- trend deterioration threshold: `absolute_change <= -10`.

## Safety Outcomes
- Confidence/freshness stop conditions are emitted in handoff payload.
- Stop conditions suppress policy eligibility in self-healing evaluation.
