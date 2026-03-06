# Execution and Cleanup Model

## Before Probe
- run baseline smoke precheck
- capture pre-probe snapshot
- evaluate probe gating and eligibility

## During Probe
- execute probe-specific action or passive query
- collect logs/channels/registration evidence as applicable
- evaluate assertions for expected state transitions

## Cleanup
- run cleanup verification checks
- classify cleanup success vs warning/failure

## After Probe
- run post-probe smoke and audit checks
- return structured evidence and phase statuses

## Validation Dimensions
- precheck passed
- action executed
- expected evidence observed
- cleanup succeeded
- post-probe checks collected
- evidence envelope returned
