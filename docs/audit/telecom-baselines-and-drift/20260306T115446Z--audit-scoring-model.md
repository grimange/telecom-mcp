# Audit Scoring Model

## Penalties
- critical: -30
- risk: -20
- warning: -10
- info: -3

## Status Mapping
- 90-100: compliant
- 75-89: acceptable
- 60-74: degraded
- <60: high_risk

## Calculation
1. start at 100
2. subtract penalty for each non-passed policy
3. clamp to [0, 100]
4. map score to status band

## Result Fields
- `score`
- `status`
- `violations`
- `drift`
- `recommendations`
