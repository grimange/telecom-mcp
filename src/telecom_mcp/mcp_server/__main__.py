from __future__ import annotations

import sys


def _run() -> int:
    try:
        from .server import run_cli
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", "unknown")
        sys.stderr.write(
            "startup_error code=VALIDATION_ERROR "
            f"message=Missing runtime dependency '{missing}'. "
            "Use the project virtualenv interpreter to run telecom_mcp.mcp_server.\n"
        )
        return 2
    return run_cli()


raise SystemExit(_run())
