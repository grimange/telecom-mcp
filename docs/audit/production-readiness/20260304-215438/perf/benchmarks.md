# Performance Benchmarks

## Scope
- Local benchmark only (mock-free, no PBX dependency)
- Tool under test: `telecom.list_targets`
- Iterations: 250

## Result Summary
- p95 latency: **0.072 ms**
- mean latency: **0.060 ms**
- min/max latency: **0.029 / 0.126 ms**

Source: `perf/results.json`.

## Notes
- This benchmark measures in-process tool dispatch + envelope/audit overhead.
- No prior PRR baseline exists in this repository yet, so regression comparison is not available for this run.
