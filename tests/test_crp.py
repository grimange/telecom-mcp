from __future__ import annotations

from telecom_mcp.crp.runner import run_crp


def test_crp_runs_and_executes_cr3(tmp_path) -> None:
    prr_root = tmp_path / "prr"
    prr_run = prr_root / "20260305-000000"
    prr_run.mkdir(parents=True)
    (prr_run / "scorecard.md").write_text(
        "# Production Readiness Scorecard\n\n**Total: 95 / 100**\n",
        encoding="utf-8",
    )

    result = run_crp(
        run_id="20260305-010101",
        output_root=str(tmp_path / "crp"),
        targets_file="docs/targets.example.yaml",
        crp_mode="mock",
        production_readiness_root=str(prr_root),
    )

    assert result.summary["scores"]["agent_readiness"] >= 90
    assert result.summary["gates"]["CR3"] is True

    base = tmp_path / "crp" / "20260305-010101"
    assert (base / "certification.md").exists()
    assert (base / "summary.json").exists()
    assert (base / "gates.md").exists()
    assert (base / "reports/agent-readiness").exists()
