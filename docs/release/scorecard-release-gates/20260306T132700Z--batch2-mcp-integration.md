# Batch 2 MCP Integration

Implemented MCP/core exposure:
- `telecom.release_gate_decision(pbx_id, context?, policy_input?, validation?)`

Integration behavior:
- derives policy input from `telecom.scorecard_policy_inputs` when not provided
- derives validation snapshot from smoke + cleanup checks when not provided
- returns deterministic decision payload from `allow|hold|escalate`

Evidence integration:
- incident evidence collection now captures `release/gate_decision`
- timeline reconstruction adds `release_gate_decision_collected` events
