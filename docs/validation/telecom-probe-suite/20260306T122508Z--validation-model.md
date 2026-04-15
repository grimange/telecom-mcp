# Active Validation Model

## Current Validation Building Blocks
- existing probe primitives: `telecom.run_registration_probe`, `telecom.run_trunk_probe`, `telecom.verify_cleanup`
- smoke and playbook integrations: `telecom.run_smoke_suite`, `telecom.run_playbook`
- audit linkage: `telecom.audit_target`

## Probe Result Envelope
- `probe`
- `pbx_id`
- `platform`
- `mode`
- `status`
- `summary`
- `phases`
- `evidence`
- `warnings`
- `captured_at`

## Environment Assumptions
- passive probes may run in inspect mode
- class-C active probes require explicit validation mode + active probe enablement + lab-safe targets
