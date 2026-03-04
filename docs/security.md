# Security

## Core rules

- Secrets are loaded from environment variables.
- Secrets are never logged or returned in tool output.
- Default operating mode is `inspect`.
- Write operations are disabled unless explicitly implemented and gated.

## Redaction

Sensitive key patterns are redacted in audit logs:

- `password`, `token`, `secret`, `authorization`

## Modes

- `inspect`: read tools only
- `plan`: read + recommendation workflows
- `execute_safe`: allowlisted safe write tools only
- `execute_full`: maintenance-only mode
