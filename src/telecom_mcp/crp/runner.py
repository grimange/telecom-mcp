"""Stage-07 Continuous Reliability Pipeline runner (CR0-CR7)."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from telecom_mcp.agent_readiness.runner import run_agent_readiness
from telecom_mcp.chaos.runner import run_chaos
from telecom_mcp.observability.runner import run_observability


@dataclass(slots=True)
class CRPRunResult:
    output_dir: Path
    badge: str
    summary: dict[str, Any]


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _parse_score(scorecard: Path) -> float | None:
    text = scorecard.read_text(encoding="utf-8")
    patterns = [
        r"Total:\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*100",
        r"Total score:\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*100",
        r"Mock Chaos Score:\s*([0-9]+(?:\.[0-9]+)?)/100",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    return None


def _latest_run_with_score(root: Path) -> tuple[Path | None, float | None]:
    if not root.exists():
        return None, None
    candidates = [d for d in root.iterdir() if d.is_dir() and (d / "scorecard.md").exists()]
    if not candidates:
        return None, None
    latest = sorted(candidates, key=lambda p: p.name)[-1]
    score = _parse_score(latest / "scorecard.md")
    return latest, score


def _copy_report_tree(src_dir: Path, dst_dir: Path) -> Path:
    out = dst_dir / src_dir.name
    shutil.copytree(src_dir, out)
    return out


def run_crp(
    *,
    run_id: str | None = None,
    output_root: str = "docs/audit/crp",
    targets_file: str = "targets.yaml",
    crp_mode: str = "mock",
    chaos_mode: str | None = None,
    production_readiness_root: str = "docs/audit/production-readiness",
) -> CRPRunResult:
    mode = crp_mode.strip().lower()
    if mode not in {"mock", "lab"}:
        raise SystemExit(f"Invalid CRP_MODE={mode}; expected mock|lab")
    effective_chaos_mode = (chaos_mode or "mock").strip().lower()
    if effective_chaos_mode not in {"mock", "lab"}:
        raise SystemExit(f"Invalid CHAOS_MODE={effective_chaos_mode}; expected mock|lab")

    stamp = run_id or _utc_stamp()
    out_dir = Path(output_root) / stamp
    out_dir.mkdir(parents=True, exist_ok=False)

    reports_root = out_dir / "reports"
    gates: dict[str, dict[str, Any]] = {}
    scores: dict[str, float] = {
        "production_readiness": 0.0,
        "observability": 0.0,
        "agent_readiness": 0.0,
        "mock_chaos": 0.0,
    }

    # CR0 preflight
    preflight_checks = {
        "implementation_plan": Path("docs/telecom-mcp-implementation-plan.md").exists(),
        "tool_spec": Path("docs/telecom-mcp-tool-specification.md").exists(),
        "agents_md": Path("AGENTS.md").exists(),
        "stage07_prompt": Path("docs/prompts/stage--07--telecom-continuous-reliability-pipeline-prompt.md").exists(),
        "stage06_prompt": Path("docs/prompts/stage--06--agent-integration-readiness-prompt.md").exists(),
    }
    cr0_pass = all(preflight_checks.values())
    _write_json(out_dir / "evidence/preflight.json", {"checks": preflight_checks, "pass": cr0_pass})
    gates["CR0"] = {"name": "Preflight", "pass": cr0_pass}

    # CR1 production readiness (reuse latest available scorecard)
    prr_src, prr_score = _latest_run_with_score(Path(production_readiness_root))
    if prr_src and prr_score is not None:
        _copy_report_tree(prr_src, reports_root / "production-readiness")
        scores["production_readiness"] = prr_score
        gates["CR1"] = {"name": "Production Readiness PRR", "pass": prr_score >= 90, "score": prr_score}
    else:
        gates["CR1"] = {
            "name": "Production Readiness PRR",
            "pass": False,
            "score": 0.0,
            "note": "No production-readiness scorecard found to evaluate.",
        }

    # CR2 observability
    obs = run_observability(
        output_root=str(reports_root / "observability"),
        targets_file=targets_file,
    )
    scores["observability"] = obs.score
    gates["CR2"] = {"name": "Observability", "pass": obs.score >= 85, "score": obs.score}

    # CR3 agent readiness (automatic)
    agent = run_agent_readiness(
        output_root=str(reports_root / "agent-readiness"),
        targets_file=targets_file,
    )
    scores["agent_readiness"] = agent.score
    gates["CR3"] = {"name": "Agent Readiness", "pass": agent.score >= 90, "score": agent.score}

    # CR4 chaos mock/lab
    chaos = run_chaos(
        output_root=str(reports_root / "chaos"),
        chaos_mode=effective_chaos_mode,
        targets_file=targets_file,
    )
    scores["mock_chaos"] = chaos.mock_score_percent
    gates["CR4"] = {"name": "Chaos", "pass": chaos.mock_score_percent >= 80, "score": chaos.mock_score_percent}

    # CR5 optional lab bundle
    if mode == "lab":
        (reports_root / "fixtures").mkdir(parents=True, exist_ok=True)
        _write_text(
            reports_root / "fixtures/lab-note.md",
            "Lab mode enabled. Fixture capture/integration add-ons are repository-optional and were not auto-run.\n",
        )
        gates["CR5"] = {"name": "Optional Lab Bundle", "pass": True, "note": "Optional phase"}
    else:
        gates["CR5"] = {"name": "Optional Lab Bundle", "pass": True, "note": "Skipped in mock mode"}

    # CR6 certification
    ops_ready = (
        gates["CR1"]["pass"] and gates["CR2"]["pass"] and gates["CR3"]["pass"] and gates["CR4"]["pass"]
    )
    telecom_grade = ops_ready and mode == "lab" and effective_chaos_mode == "lab"
    badge = "TELECOM GRADE" if telecom_grade else ("OPS READY" if ops_ready else "NOT READY")

    summary = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "crp_mode": mode,
        "chaos_mode": effective_chaos_mode,
        "scores": scores,
        "badge": badge,
        "gates": {k: v["pass"] for k, v in gates.items()},
    }
    _write_json(out_dir / "summary.json", summary)

    cert_lines = [
        "# Telecom CRP Certification",
        "",
        f"- Timestamp: {summary['timestamp']}",
        f"- CRP_MODE: {mode}",
        f"- CHAOS_MODE: {effective_chaos_mode}",
        f"- Badge: {badge}",
        "",
        "## Scores",
        f"- Production Readiness: {scores['production_readiness']}",
        f"- Observability: {scores['observability']}",
        f"- Agent Readiness: {scores['agent_readiness']}",
        f"- Mock Chaos: {scores['mock_chaos']}",
        "",
        "## Gate Criteria",
        "- PRR >= 90",
        "- Observability >= 85",
        "- Agent Readiness >= 90",
        "- Mock Chaos >= 80",
    ]
    _write_text(out_dir / "certification.md", "\n".join(cert_lines) + "\n")

    gate_lines = ["# CRP Gates", ""]
    for key in sorted(gates):
        item = gates[key]
        status = "PASS" if item["pass"] else "FAIL"
        extra = ""
        if "score" in item:
            extra = f" (score={item['score']})"
        if "note" in item:
            extra = f"{extra} - {item['note']}"
        gate_lines.append(f"- {key} {item['name']}: {status}{extra}")
    _write_text(out_dir / "gates.md", "\n".join(gate_lines) + "\n")

    # CR7 remediation
    if not ops_ready:
        remediation = [
            "# CRP Remediation",
            "",
            "1. Raise Production Readiness score to >= 90.",
            "2. Keep Observability >= 85.",
            "3. Keep Agent Readiness >= 90.",
            "4. Keep Mock Chaos >= 80.",
            "5. Re-run `python scripts/crp_run.py` after fixes.",
        ]
        _write_text(out_dir / "remediation/crp-remediation.md", "\n".join(remediation) + "\n")

    return CRPRunResult(output_dir=out_dir, badge=badge, summary=summary)
