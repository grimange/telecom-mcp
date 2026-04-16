# Decision and Gating Model

## Decision Inputs
- runtime mode
- target metadata/tags
- pre-action smoke/playbook/audit signals
- policy retry budget and cooldown state
- action risk class and environment permissions

## Gating Rules
- policy platform compatibility required
- remediation-mode policies require `execute_safe|execute_full`
- class-B/C policies require `TELECOM_MCP_ENABLE_SELF_HEALING=1`
- lab-only policies require lab/test-safe target eligibility unless explicitly supported otherwise

## Stop Conditions
- cooldown active
- retry budget exhausted
- gating failure
- verification failure after action

## Escalation Triggers
- no-act high-risk policy
- action failure
- post-action verification failure
- safety/gating violations
