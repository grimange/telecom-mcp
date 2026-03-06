# Self-Healing Model

## Policy Schema
- `policy_id`
- `title`
- `purpose`
- `platform_scope`
- `risk_class`
- `requires_remediation_mode`
- `supports_fixture_mode`
- `supports_lab_mode`
- `supports_production_mode`
- retry/cooldown controls

## Result Envelope
- `policy`
- `pbx_id`
- `platform`
- `mode`
- `status`
- `summary`
- `phases`
- `evidence`
- `warnings`
- `captured_at`
- `escalation`

## Phases
- `precheck`
- `gating`
- `decision`
- `act`
- `verify`
