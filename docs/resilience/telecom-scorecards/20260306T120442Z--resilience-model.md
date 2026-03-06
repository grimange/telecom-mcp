# Telecom Resilience Model

## Dimensions
1. Configuration Integrity (weight 20)
2. Runtime Health (weight 20)
3. Detection Readiness (weight 15)
4. Validation Confidence (weight 15)
5. Fault Resilience (weight 15)
6. Incident Burden (weight 15)

## Score Levels
- `target_score` (PBX)
- `cluster_score`
- `environment_score`

## Design Principles
- explainable inputs and deductions
- no hidden scoring factors
- confidence overlays for incomplete evidence
- critical findings can cap final score
