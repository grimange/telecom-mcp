# Security and Gating Fixes

## findings addressed
- `SEC-01` / `RSG-01`: fixed.
- `SEC-02` / `RSG-02`: fixed.
- `SEC-03`: fixed.
- `SEC-04`: fixed.
- `SEC-05`: fixed.

## code areas changed
- `src/telecom_mcp/tools/telecom.py`
  - added export redaction/bounding pipeline for `telecom.export_evidence_pack`
  - added explicit target eligibility model usage for active gating
  - added environment membership enforcement helper for rollups/promotion
  - added filesystem-backed persistence hooks for scorecard/release/evidence stores
- `src/telecom_mcp/config.py`
  - extended target model with `safety_tier` and `allow_active_validation`
  - validated environment/safety metadata shape
- Connectors
  - `src/telecom_mcp/connectors/asterisk_ami.py`
  - `src/telecom_mcp/connectors/asterisk_ari.py`
  - `src/telecom_mcp/connectors/freeswitch_esl.py`
  - each now includes bounded retry/backoff for transient failures

## hardening improvements
- Export path is now sanitized and bounded before return across `json` and `zip` formats.
- Active flows require explicit lab-safe metadata; permissive tag/untagged fallback removed.
- Environment-level decisions now fail on mixed-environment target sets.
- Connector paths now retry transient faults once with bounded backoff.
- Governance history/evidence data now persists via `TELECOM_MCP_STATE_DIR` (default `.telecom_mcp/state`).

## residual risks
- Persistence layer is local-file JSON without multi-process locking semantics.
- Release profile still reports skipped MCP stdio tests when `mcp` dependency missing in runtime.

## intentionally deferred issues
- CI policy to hard-fail on MCP skip (`OP-04` / `TEST-02`) not implemented in this batch.
- richer governance dashboard trace UX (`OP-01`) deferred.
