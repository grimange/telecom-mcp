# Policy Catalog

Implemented policies:
1. `safe_sip_reload_refresh`
2. `gateway_profile_rescan`
3. `observability_refresh_retry`
4. `post_change_validation_failure_recovery`
5. `drift_triggered_lab_recovery`
6. `escalate_only_high_risk`

Per policy metadata includes:
- risk class
- platform scope
- remediation-mode requirement
- fixture/lab/production support flags
- max retries and cooldown window

Execution model:
- pre-evidence capture
- gating + decision checks
- bounded action or no-act escalation
- post-action verification and cleanup
- optional escalation evidence pack linkage
