from __future__ import annotations

import os

if os.getenv("TELECOM_MCP_LEGACY_LINE_PROTOCOL", "0").strip() == "1":
    from .server import run_cli
else:
    from .mcp_server.server import run_cli

raise SystemExit(run_cli())
