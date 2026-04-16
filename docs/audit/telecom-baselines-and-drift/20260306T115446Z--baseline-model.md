# Baseline Model

## Observable State
- `telecom.summary`: channel/registration summaries and confidence hints
- `telecom.inventory`: baseline/posture fields including module posture
- `asterisk.version` / `freeswitch.version`
- `asterisk.modules` / `freeswitch.modules`
- `telecom.endpoints`, `telecom.registrations`, `telecom.channels`, `telecom.logs`

## Normalizable Attributes
- platform, version, module set, endpoint count, registration count, channel visibility, log accessibility
- critical module gaps and risky module signals via posture

## Vendor-Specific Attributes
- bridge query depth (Asterisk-focused)
- transport/security details that require richer PBX-native config surfaces

## Baseline Feasibility
- feasible as read-only baseline from live telemetry snapshots
- supports platform defaults and target-specific captured baselines

## Audit Limitations
- some SIP security controls (for example anonymous guest flags) are heuristic without raw config parsers
- TLS posture signal is currently inferred from inventory surface
- cross-runtime baseline store is in-memory by design for now

## Baseline Schema
- `baseline_id`
- `baseline_version`
- `platform`
- `version_min`
- `rules`
- `severity_profile`
- `state`
- `captured_from`
