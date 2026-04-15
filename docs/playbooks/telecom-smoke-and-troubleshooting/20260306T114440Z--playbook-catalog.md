# Troubleshooting Playbook Catalog (Stage-02)

## 1) sip_registration_triage
- Purpose: Diagnose endpoint registration/unreachability.
- Inputs:
  - required: `pbx_id`, `endpoint`
  - optional: vendor-specific hints via `params`
- Step sequence:
  - health check
  - endpoint inspection
  - registration/contact inspection
  - logs inspection
  - bucket classification
- Vendor branching notes:
  - uses platform health tool (`asterisk.health` or `freeswitch.health`)
- Expected output buckets:
  - `endpoint_missing`
  - `endpoint_present_but_no_contacts`
  - `endpoint_present_unavailable`
  - `endpoint_present_with_active_contacts`
  - `pbx_unhealthy`
  - `insufficient_evidence`
- Limitations: relies on normalized registration inventory quality.
- Risk classification: read-only

## 2) outbound_call_failure_triage
- Purpose: Diagnose outbound call attempts not progressing.
- Inputs:
  - required: `pbx_id`
  - optional: `endpoint`, `destination_hint`, `channel_id`, `window`
- Step sequence:
  - health
  - calls/channels
  - bridge inspection (Asterisk)
  - channel detail probe when available
  - logs inspection
  - bucket classification
- Vendor branching notes:
  - bridge-specific check only on Asterisk.
- Expected output buckets:
  - `no_call_attempt_observed`
  - `call_attempt_created_but_not_answered`
  - `bridge_never_formed`
  - `hangup_cause_indicated_in_logs`
  - `insufficient_evidence`
- Limitations: logs are signal-based and may be sparse.
- Risk classification: read-only

## 3) inbound_delivery_triage
- Purpose: Diagnose inbound delivery failure after PBX ingress.
- Inputs:
  - required: `pbx_id`
  - optional: `did`, `target`, `window`
- Step sequence:
  - health
  - channels
  - bridge state
  - registration/delivery state
  - logs
  - bucket classification
- Vendor branching notes:
  - Asterisk includes explicit bridge inspection.
- Expected output buckets:
  - `no_inbound_activity_observed`
  - `inbound_reached_pbx_but_not_ringing_endpoint`
  - `endpoint_unavailable`
  - `queue_bridge_stage_suspected`
  - `insufficient_evidence`
- Limitations: queue-specific insight depends on upstream normalized fields.
- Risk classification: read-only

## 4) orphan_channel_triage
- Purpose: Detect stale channels and suspected orphan bridge/channel relations.
- Inputs:
  - required: `pbx_id`
  - optional: `age_threshold_s` (default 600)
- Step sequence:
  - channel collection
  - bridge collection
  - correlation
  - stale/orphan heuristics
  - classification
- Vendor branching notes:
  - orphan bridge correlation available for Asterisk bridge data.
- Expected output buckets:
  - `no_anomaly_detected`
  - `orphan_channel_suspected`
  - `stuck_bridge_suspected` (reserved)
  - `cleanup_lag_suspected`
  - `pbx_query_incomplete`
- Limitations: stale detection depends on duration fields in source payload.
- Risk classification: read-only

## 5) pbx_drift_comparison
- Purpose: Compare two PBX targets for operational drift.
- Inputs:
  - required: `pbx_a`, `pbx_b`
- Step sequence:
  - run normalized compare
  - inspect differences and drift categories
  - classify drift bucket
- Vendor branching notes:
  - none; uses cross-platform compare abstraction.
- Expected output buckets:
  - `no_meaningful_drift`
  - `informational_drift`
  - `risky_drift`
  - `comparison_incomplete`
- Limitations: quality bounded by source inventory completeness.
- Risk classification: read-only
