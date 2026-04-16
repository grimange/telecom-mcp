# Score-to-Policy Mapping

## Rule Catalog

### Rule: Observability Degradation
- Trigger signals: Runtime Health <= 64 and Detection Readiness <= 69
- Minimum confidence: `medium`
- Minimum freshness: `fresh`
- Excluded conditions: confidence low/unknown, stale/unknown freshness
- Suggested candidates: `observability_refresh_retry`
- Forced no-act: yes, when confidence/freshness not satisfied
- Escalation: optional on repeated failures

### Rule: Stale Runtime State Recovery Candidate
- Trigger signals: Runtime Health <= 64 and Validation Confidence >= 60
- Minimum confidence: `high`
- Minimum freshness: `fresh`
- Excluded conditions: low confidence, stale scorecard
- Suggested candidates: `safe_sip_reload_refresh`, `gateway_profile_rescan`
- Forced no-act: yes, if mandatory prechecks not met
- Escalation: yes if action fails or confidence degrades

### Rule: Severe Drift / Security Posture
- Trigger signals: Configuration Integrity <= 55
- Minimum confidence: `high` preferred (still no-action if lower)
- Minimum freshness: any
- Excluded conditions: none
- Suggested candidates: none
- Forced no-act: `high_risk_integrity_no_automation`
- Escalation: `escalate_high_risk_drift_change`

### Rule: Post-Change Instability
- Trigger signals: trend deterioration (`absolute_change <= -10`) + low Runtime Health + low Validation Confidence
- Minimum confidence: `medium`
- Minimum freshness: `fresh`
- Excluded conditions: stale scorecard, low confidence
- Suggested candidates: `post_change_validation_failure_recovery`
- Forced no-act: yes when confidence/freshness fails
- Escalation: yes if recovery not verified

### Rule: Incident Burden Escalation
- Trigger signals: Incident Burden <= 60
- Minimum confidence: any
- Minimum freshness: any
- Excluded conditions: none
- Suggested candidates: none by default
- Forced no-act: optional based on confidence
- Escalation: `incident_burden_escalation`

## Mapping Principles Enforced
- Dimension-level signals drive mapping
- Confidence/freshness required for action-oriented recommendations
- Trend used for priority weighting only
- Cleanup/validation weakness reduces active remediation candidates
- Low validation confidence biases no-act/evidence-refresh
