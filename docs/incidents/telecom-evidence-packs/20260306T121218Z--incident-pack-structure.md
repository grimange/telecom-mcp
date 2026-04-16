# Incident Pack Structure

Implemented logical structure:

incident-pack/
- metadata.json
- summary.md
- timeline.json
- evidence_items.json

Evidence source group references:
- `pbx-state/*`
- `calls/*`
- `sip/*`
- `logs/*`
- `validation/*`
- `audits/*`
- `vendor/*`

Export support:
- JSON: full structured pack payload
- Markdown: operator summary view
- ZIP: manifest-oriented payload (stage representation)
