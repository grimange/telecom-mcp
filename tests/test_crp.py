from __future__ import annotations

from types import SimpleNamespace

import telecom_mcp.crp.runner as crp_runner

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


def test_crp_lab_mode_does_not_imply_lab_chaos(tmp_path, monkeypatch) -> None:
    prr_root = tmp_path / "prr"
    prr_run = prr_root / "20260305-000000"
    prr_run.mkdir(parents=True)
    (prr_run / "scorecard.md").write_text(
        "# Production Readiness Scorecard\n\n**Total: 95 / 100**\n",
        encoding="utf-8",
    )

    captured: dict[str, str] = {}

    def _fake_run_chaos(*, output_root: str, chaos_mode: str | None, targets_file: str):
        captured["chaos_mode"] = str(chaos_mode)
        out_dir = tmp_path / "fake-chaos" / "20260305-010101" / "chaos"
        out_dir.mkdir(parents=True)
        return SimpleNamespace(
            output_dir=out_dir,
            mock_score_percent=85.0,
            readiness="OPS READY",
        )

    monkeypatch.setattr(crp_runner, "run_chaos", _fake_run_chaos)

    result = run_crp(
        run_id="20260305-020202",
        output_root=str(tmp_path / "crp"),
        targets_file="docs/targets.example.yaml",
        crp_mode="lab",
        production_readiness_root=str(prr_root),
    )

    assert captured["chaos_mode"] == "mock"
    assert result.summary["chaos_mode"] == "mock"
