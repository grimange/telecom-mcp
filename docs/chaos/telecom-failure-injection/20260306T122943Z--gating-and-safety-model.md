# Gating and Safety Model

## Safety Classes
- Class A: fixture-first low-risk simulations
- Class B: lab-only controlled mutation simulations
- Class C: reserved for active validation extensions (not expanded in this stage)

## Gating Inputs
- scenario/platform compatibility
- execution mode (`fixture|lab`)
- lab mode requires `TELECOM_MCP_ENABLE_CHAOS=1`
- lab mode requires lab/test-safe target metadata
- scenario-level `requires_gated_mode` checks execute mode (`execute_safe|execute_full`)

## Guardrails
- read-only by default
- no unrestricted command execution
- explicit gating failure reporting in result envelope
- rollback and postcheck phases always represented
