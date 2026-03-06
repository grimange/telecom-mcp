# Evidence Correlation Model

## Timeline Reconstruction Inputs
- registrations evidence rows
- channel/call evidence rows
- log evidence windows
- smoke/playbook/audit result states

## Correlation Events
- `registration_state_observed`
- `channel_state_observed`
- `call_state_observed`
- `log_window_collected`
- `smoke_result_collected`
- `playbook_result_collected`
- `audit_result_collected`

## Ordering
- all events normalized into timeline events with deterministic `time` field
- timeline sorted ascending by timestamp

## Goal
Provide explainable sequence evidence for “what changed when” during incidents.
