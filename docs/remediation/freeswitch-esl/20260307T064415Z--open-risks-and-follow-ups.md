# Open Risks and Follow-Ups

## Open Risks
1. Real-PBX validation has not been run in this remediation turn; behavior is validated only through mocked tests.
2. Sofia parsing remains heuristic and may require grammar-tight parsing against more production captures.
3. Full repository test suite includes unrelated readiness/CRP score assertions currently failing in this environment baseline.

## Follow-Ups
1. Run the next pipeline: `Validate FreeSWITCH ESL Against Real PBX Targets` and attach packet/frame evidence.
2. Expand replay fixtures from real `sofia status` variants and malformed edge payloads.
3. Add an explicit health data-quality flag for protocol/frame integrity at tool output level (if contract allows additive field).
