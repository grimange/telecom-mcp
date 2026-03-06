# Audit Policy Catalog

## System Integrity
- `PBX_VERSION_SUPPORTED`
- `REQUIRED_MODULES_LOADED`
- `MODULES_MISSING`

## SIP Security
- `ANONYMOUS_SIP_DISABLED`
- `TLS_AVAILABLE`
- `WEAK_TRANSPORTS_DETECTED`

## Endpoint Integrity
- `ENDPOINTS_PRESENT`
- `REGISTRATIONS_VISIBLE`
- `REGISTRATION_FAILURE_RATE`
- `CONTACT_STALENESS`

## Operational Observability
- `CHANNEL_QUERY_AVAILABLE`
- `LOG_ACCESS_AVAILABLE`
- `BRIDGE_QUERY_AVAILABLE`

## Configuration Drift Indicators
- `BASELINE_VERSION_MISMATCH`
- `MODULE_SET_DRIFT`
- `ENDPOINT_INVENTORY_DRIFT`
- `REGISTRATION_PATTERN_DRIFT`

Each policy includes:
- policy_id
- title
- platform
- severity
- description
- evaluation_method
- evidence_fields
- recommended_action
