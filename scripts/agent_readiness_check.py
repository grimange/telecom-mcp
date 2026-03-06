#!/usr/bin/env python3
"""Execute telecom agent-readiness phases (A0-A5) and write timestamped artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telecom_mcp.agent_readiness.runner import run_agent_readiness


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run telecom agent-readiness pipeline")
    parser.add_argument(
        "--run-id", default=None, help="Optional YYYYMMDD-HHMMSS output folder"
    )
    parser.add_argument(
        "--output-root",
        default="docs/audit/agent-readiness",
        help="Base directory for timestamped output",
    )
    parser.add_argument(
        "--targets-file",
        default="targets.yaml",
        help="Targets file used for offline agent-readiness checks",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_agent_readiness(
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
