from __future__ import annotations

from telecom_mcp.agent_readiness.runner import run_agent_readiness


def test_agent_readiness_pipeline_smoke(tmp_path) -> None:
    output_root = tmp_path / "audit"
    result = run_agent_readiness(
        run_id="20260305-000000",
        output_root=str(output_root),
        targets_file="docs/targets.example.yaml",
    )

    assert result.passed is True
    assert result.score >= 90

    base = output_root / "20260305-000000"
    assert (base / "scorecard.md").exists()
    assert (base / "findings.md").exists()

    evidence = base / "evidence"
    assert (evidence / "preflight.json").exists()
    assert (evidence / "tool-contract-smoke.json").exists()
    assert (evidence / "error-contract.json").exists()
    assert (evidence / "mode-gating.json").exists()
    assert (evidence / "agent-workflow.json").exists()
    assert (evidence / "docs-check.json").exists()
