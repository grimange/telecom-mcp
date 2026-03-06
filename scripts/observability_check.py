#!/usr/bin/env python3
"""Execute telecom observability phases (O0-O7) and write timestamped artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telecom_mcp.observability.runner import run_observability


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run telecom observability pipeline")
    parser.add_argument(
        "--run-id", default=None, help="Optional YYYYMMDD-HHMMSS output folder"
    )
    parser.add_argument(
        "--output-root",
        default="docs/audit/observability",
        help="Base directory for timestamped output",
    )
    parser.add_argument(
        "--targets-file",
        default="docs/targets.example.yaml",
        help="Targets file for offline observability checks",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_observability(
        run_id=args.run_id,
        output_root=args.output_root,
        targets_file=args.targets_file,
    )
    print(
        json.dumps(
            {
                "output_dir": str(result.output_dir),
                "score": result.score,
                "passed": result.passed,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
