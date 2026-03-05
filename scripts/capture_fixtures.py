#!/usr/bin/env python3
"""Capture and sanitize telecom fixtures from lab targets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from telecom_mcp.config import load_settings
from telecom_mcp.errors import ToolError
from telecom_mcp.fixtures.capture import FixtureCaptureRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture telecom fixtures")
    parser.add_argument("--targets-file", default="targets.yaml")
    parser.add_argument("--output-root", default="docs/fixtures")
    parser.add_argument("--pbx-id", action="append", dest="pbx_ids", default=[])
    parser.add_argument("--endpoint", default="1001")
    parser.add_argument("--timeout", type=float, default=4.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.targets_file, mode="inspect")
        runner = FixtureCaptureRunner(
            settings,
            output_root=Path(args.output_root),
            pbx_ids=args.pbx_ids or None,
            endpoint=args.endpoint,
            timeout_s=args.timeout,
        )
        report = runner.run()
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
        return 0
    except ToolError as exc:
        sys.stderr.write(f"capture_error code={exc.code} message={exc.message}\n")
        if exc.details:
            sys.stderr.write(json.dumps(exc.details, indent=2) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
