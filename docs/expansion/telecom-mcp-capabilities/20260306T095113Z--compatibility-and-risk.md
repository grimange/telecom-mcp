# Compatibility and Risk

Timestamp: `20260306T095113Z`

## Schema normalization decisions

New Batch 1 vendor-neutral tools return:
- `pbx_id`
- `platform`
- `tool`
- `summary`
- `items`
- `counts`
- `warnings`
- `truncated`
- `captured_at`
- `source_command` (for log tools)

## Backward compatibility strategy

- No existing tool names were removed.
- Existing tool argument shapes remain valid.
- New wrappers are additive and call existing vendor tools internally.
- Existing payload shapes for older tools are preserved.

## Risk assessment

- Log retrieval risk: controlled by explicit per-target `logs.path`; no arbitrary shell execution introduced.
- Parser risk: contacts/version parsing may vary by PBX output format; tests added for representative samples.
- Inventory risk: currently summary-oriented; not full module drift auditing yet.

## Deprecation recommendations

- No immediate deprecations.
- Prefer `telecom.*` wrappers for agent workflows; keep vendor tools for deep diagnostics.
