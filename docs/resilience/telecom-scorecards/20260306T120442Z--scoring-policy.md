# Scoring Policy

## Weighting
- Configuration Integrity: 20
- Runtime Health: 20
- Detection Readiness: 15
- Validation Confidence: 15
- Fault Resilience: 15
- Incident Burden: 15

## Score Bands
- 90-100: Strong
- 75-89: Acceptable
- 60-74: Degraded
- <60: At Risk

## Severity Influence
- critical > risk > warning > info for negative signal weighting
- critical negative findings can cap total score at degraded band

## Confidence Overlay
Every scorecard includes:
- `score`
- `confidence` (`high|medium|low`)
- `confidence_reasons`

Confidence depends on:
- evidence completeness ratio
- missing/deferred evidence families
- subcall failure/degraded collection signals
