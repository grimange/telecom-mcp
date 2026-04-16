# Drift Detection Model

## Comparison Modes
- baseline vs PBX: `telecom.drift_target_vs_baseline`
- PBX vs PBX: `telecom.drift_compare_targets`
- snapshot vs snapshot: existing `telecom.diff_snapshots`

## Drift Categories
- `NONE`
- `INFO`
- `WARNING`
- `RISK`
- `CRITICAL`

## Drift Inputs
- baseline required modules and version thresholds
- live state counts and visibility
- module posture signals and cross-target diff categories

## Drift Output Shape
- finding list with `policy_id`, `severity`, `category`, `message`, `evidence`
- summary counts and warnings
- deterministic timestamp

## Notes
- drift classification is policy-severity-driven and deterministic
- partial collection is represented via `failed_sources` and warning annotations
