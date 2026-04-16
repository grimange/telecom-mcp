# Batch 3 History Analytics

Release gate history tracking now stores decision snapshots per entity:
- entity key: `pbx:<id>` or `environment:<id>`
- stored fields: timestamp, decision payload, score/confidence/freshness summary

`telecom.release_gate_history` returns:
- counts by decision (`allow`, `hold`, `escalate`)
- recent entries (bounded by `limit`)
- simple trend marker from latest vs previous decision
