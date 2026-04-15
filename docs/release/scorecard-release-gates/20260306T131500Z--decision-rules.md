# Decision Rules

## Hold Rules
- `confidence in {low, unknown}` => hold
- `freshness != fresh` => hold
- `policy_handoff.stop_conditions not empty` => hold
- smoke not passed => hold
- post-change status failed/warning => hold
- cleanup verification false => hold
- conflicting evidence => hold
- high-risk change with score < 85 => hold

## Escalate Rules
- scorecard recommended escalations present => escalate
- score <= 55 with high confidence => escalate

## Allow Rule
- all hold/escalate conditions absent => allow
