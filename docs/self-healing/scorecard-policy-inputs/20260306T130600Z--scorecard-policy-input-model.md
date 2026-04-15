# Scorecard Policy Input Model

## Available Scorecard Signal Inventory

### Configuration Integrity
- Source fields: `dimensions[name=Configuration Integrity].score`, `negative_signals`, `warnings`
- Classification: safe decision hint + escalation hint
- Mandatory for: high-risk drift/security escalation suppression logic

### Runtime Health
- Source fields: `dimensions[name=Runtime Health].score`, `warnings`
- Classification: safe decision hint
- Mandatory for: observability refresh and runtime low-risk candidate selection

### Detection Readiness
- Source fields: `dimensions[name=Detection Readiness].score`, `negative_signals`
- Classification: safe decision hint
- Optional/advisory for: observability-driven prioritization

### Validation Confidence
- Source fields: `dimensions[name=Validation Confidence].score`, `confidence`
- Classification: verification-only hint + safe decision hint
- Mandatory for: lab-only policy recommendation posture

### Fault Resilience
- Source fields: `dimensions[name=Fault Resilience].score`
- Classification: escalation hint
- Advisory for: no-act preference in ambiguous fault scenarios

### Incident Burden
- Source fields: `dimensions[name=Incident Burden].score`
- Classification: escalation hint
- Mandatory for: repeated incident escalation recommendation

### Global Scorecard Fields
- `score`: advisory only, never sole authorization signal
- `band`: advisory categorization only
- `confidence`: mandatory gating signal
- `confidence_reasons`: mandatory explanation signal
- `generated_at`: mandatory freshness signal
- `trend_summary.absolute_change`: prioritization signal, not authorization

## Unsupported/Unsafe Remediation Influence
- Any signal that bypasses target eligibility/mode/cooldown/retry controls
- Any inference from missing evidence interpreted as permission to act

## Missing Metadata Requirements for Safe Use
- dimension-level freshness timestamps (currently inferred from scorecard timestamp)
- explicit evidence refs per dimension from upstream tools
- explicit entity scope tags (lab/fixture/production)
- explicit conflict markers for contradictory evidence

## Policy Input Schema

Generated policy input fields:
- `entity_type`
- `entity_id`
- `score`
- `band`
- `confidence`
- `confidence_reasons`
- `freshness`
- `freshness_reasons`
- `dimension_signals`
- `recommended_policy_candidates`
- `recommended_no_act_candidates`
- `recommended_escalations`
- `required_prechecks`
- `required_evidence_refresh`
- `warnings`
- `generated_at`
- `policy_handoff`

Dimension signal fields:
- `dimension_name`
- `dimension_score`
- `dimension_confidence`
- `risk_level`
- `trend`
- `supporting_evidence_refs`
- `policy_relevance`
- `recommended_action_posture`

Action postures:
- `no_action`
- `collect_more_evidence`
- `evaluate_low_risk_policy`
- `evaluate_lab_only_policy`
- `escalate_only`
