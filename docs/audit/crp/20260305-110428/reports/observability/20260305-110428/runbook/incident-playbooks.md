# Incident Playbooks

## Endpoint unreachable
- Symptoms: endpoint state becomes `Unavailable`, call setup fails for one extension or a subset.
- Likely causes: endpoint network path loss, registration expired, contact drift, ACL/firewall changes.
- Tools to run: `asterisk.pjsip_show_endpoint`, `asterisk.pjsip_show_endpoints`, `telecom.capture_snapshot`.
- Interpretation: no contacts or long RTT indicates endpoint-side/network issue; broad impact indicates PBX-side issue.
- Escalation/Rollback: escalate to voice platform + network on-call, avoid config writes in `inspect` mode.

## Trunk down or registration rejected
- Symptoms: outbound/inbound trunk failures, registration state `Rejected/Unregistered`.
- Likely causes: provider auth mismatch, SBC reachability, DNS/TLS failures.
- Tools to run: `asterisk.pjsip_show_registration`, `freeswitch.gateway_status`, `telecom.summary`.
- Interpretation: repeated reject states indicate credential/provider policy issue; intermittent states indicate transport instability.
- Escalation/Rollback: engage carrier NOC with correlation IDs and snapshot evidence.

## AMI/ARI/ESL disconnect storm
- Symptoms: spikes in connection failures, health checks intermittently fail.
- Likely causes: control-plane saturation, socket exhaustion, firewall flaps, service restarts.
- Tools to run: `asterisk.health`, `freeswitch.health`, `telecom.capture_snapshot`.
- Interpretation: concurrent failures across protocols suggest host/network issue, single-protocol failures indicate connector path issue.
- Escalation/Rollback: pause non-essential polling, notify infra on-call, validate rate-limit behavior.

## Timeout storm (upstream slowness)
- Symptoms: rising `TIMEOUT` errors with degraded tool latency.
- Likely causes: PBX overload, dependency slowness, network congestion.
- Tools to run: `telecom.summary`, `asterisk.active_channels`, `freeswitch.channels`.
- Interpretation: timeout + high active channels implies saturation; timeout + low load implies transport or dependency latency.
- Escalation/Rollback: scale down polling pressure, open incident with SRE/telecom ops.

## Rate limiting triggered
- Symptoms: `NOT_ALLOWED` with rate-limit details in tool response.
- Likely causes: bursty client behavior, automation loop, concurrent incident tooling.
- Tools to run: `telecom.summary` and inspect rate-limit errors in audit logs.
- Interpretation: repeated blocks for one scope indicate caller burst; distributed blocks indicate broad tooling pressure.
- Escalation/Rollback: throttle callers, stagger diagnostics, maintain read-only posture.

## Parsing errors due to version differences
- Symptoms: `UPSTREAM_ERROR` from malformed/unexpected payload fields.
- Likely causes: PBX upgrade changed response format, optional fields missing.
- Tools to run: `telecom.capture_snapshot`; then fixture workflow from `docs/runbook.md`.
- Interpretation: isolated parser break confirms normalization drift; compare sanitized fixtures before/after change.
- Escalation/Rollback: create compatibility parser update and fixture regression tests.

