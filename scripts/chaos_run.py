#!/usr/bin/env python3
"""Execute telecom chaos PRR phases and write timestamped artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telecom_mcp.chaos.runner import run_chaos


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run telecom chaos PRR")
    parser.add_argument("--run-id", default=None, help="Optional YYYYMMDD-HHMMSS run folder")
    parser.add_argument(
        "--output-root",
        default="docs/audit/production-readiness",
        help="Base directory for timestamped audit output",
    )
    parser.add_argument(
        "--chaos-mode",
        default=None,
        choices=["mock", "lab"],
        help="Override CHAOS_MODE env (default: mock)",
    )
    parser.add_argument(
        "--targets-file",
        default="targets.yaml",
        help="Targets file to use for chaos runs (default: targets.yaml)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_chaos(
        run_id=args.run_id,
        output_root=args.output_root,
        chaos_mode=args.chaos_mode,
        targets_file=args.targets_file,
    )
    print(
        json.dumps(
            {
                "output_dir": str(result.output_dir),
                "mock_score_percent": result.mock_score_percent,
                "readiness": result.readiness,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
