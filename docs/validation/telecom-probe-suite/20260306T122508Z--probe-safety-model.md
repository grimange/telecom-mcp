# Probe Safety Model

## Safety Classes
- Class A: fixture/passive validation
- Class B: lab-safe passive/low-impact probes
- Class C: lab-only active call/route probes

## Gating Inputs
- allowed mode (`execute_safe|execute_full` for class C)
- active probe enable flag (`TELECOM_MCP_ENABLE_ACTIVE_PROBES=1`)
- lab-safe target eligibility (`tags`/`validation_safe` or explicit override env)
- platform scope enforcement

## Risk Boundaries
- no unrestricted command execution
- no production probing by default
- bounded probe args (`timeout_s` cap)
- cleanup verification phase included
