# Follow-up Actions

1. Deploy current repository head to the runtime serving MCP telecom tools, then rerun this validation pipeline.
2. Re-validate `freeswitch.health`; current `TypeError` path is the top operational blocker.
3. Re-validate `freeswitch.version`; parsed version should match raw `1.10.11-release`.
4. Re-check `freeswitch.sofia_status` completeness after deployment (expect closer alignment to raw table output).
5. Decide whether BGAPI validation is in scope; if yes, add a gated validation-only BGAPI pathway.
