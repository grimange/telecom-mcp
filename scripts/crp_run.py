#!/usr/bin/env python3
"""Execute telecom Continuous Reliability Pipeline (CRP)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telecom_mcp.crp.runner import run_crp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run telecom Continuous Reliability Pipeline")
    parser.add_argument("--run-id", default=None, help="Optional YYYYMMDD-HHMMSS output folder")
    parser.add_argument("--output-root", default="docs/audit/crp", help="Base output directory")
    parser.add_argument("--targets-file", default="targets.yaml", help="Targets file")
    parser.add_argument("--crp-mode", default="mock", choices=["mock", "lab"], help="CRP mode")
    parser.add_argument(
        "--chaos-mode",
        default=None,
        choices=["mock", "lab"],
        help="Optional override for chaos phase mode",
    )
    parser.add_argument(
        "--production-readiness-root",
        default="docs/audit/production-readiness",
        help="Path where existing PRR artifacts live",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_crp(
        run_id=args.run_id,
        output_root=args.output_root,
        targets_file=args.targets_file,
        crp_mode=args.crp_mode,
        chaos_mode=args.chaos_mode,
        production_readiness_root=args.production_readiness_root,
    )
    print(
        json.dumps(
            {
                "output_dir": str(result.output_dir),
                "badge": result.badge,
                "summary": result.summary,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
