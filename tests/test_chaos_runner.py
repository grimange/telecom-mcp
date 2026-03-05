from __future__ import annotations

from pathlib import Path

from telecom_mcp.chaos.runner import run_chaos


def test_run_chaos_creates_required_artifacts(tmp_path: Path) -> None:
    result = run_chaos(
        run_id="20990101-000000",
        output_root=str(tmp_path),
        chaos_mode="mock",
        targets_file="docs/targets.example.yaml",
    )
    out = result.output_dir

    assert (out / "evidence/chaos-preflight.json").exists()
    assert (out / "evidence/mock-chaos-results.jsonl").exists()
    assert (out / "evidence/mock-chaos-audit-log.txt").exists()
    assert (out / "evidence/rate-limit-results.json").exists()
    assert (out / "evidence/backpressure-results.json").exists()
    assert (out / "evidence/write-guardrail-tests.json").exists()
    assert (out / "chaos-scorecard.md").exists()
