# Chaos Scenario Catalog

Implemented scenarios:
1. `sip_registration_loss`
2. `registration_flapping`
3. `trunk_gateway_outage`
4. `orphan_channel_accumulation`
5. `stuck_bridge_simulation`
6. `module_availability_failure`
7. `observability_degradation`
8. `drift_injection_fixture`

Per-scenario metadata includes:
- failure class (`risk_class` A/B)
- supported modes (`fixture`, optional `lab`)
- gating requirements
- expected playbook/smoke/audit detections

Execution linkage:
- inject -> observe -> rollback -> postcheck
- detection verification via playbook/smoke/audit calls
