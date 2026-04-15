# Evidence Pack Model

## Required Fields
- `incident_id`
- `pbx_id`
- `platform`
- `incident_type`
- `collection_time`
- `collector`
- `collection_mode`
- `evidence_items`
- `timeline`
- `integrity_hash`
- `warnings`

## Evidence Item Schema
- `evidence_id`
- `source`
- `type`
- `collection_method`
- `timestamp`
- `tool_used`
- `data_reference`
- `hash`
- `notes`

## Integrity
- each evidence item has deterministic SHA-256 hash
- pack integrity hash is derived from incident metadata + item hashes + timeline
