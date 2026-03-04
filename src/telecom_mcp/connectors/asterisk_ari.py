"""ARI connector with strict timeout and error mapping."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from typing import Any

from ..config import ARIConfig
from ..errors import (
    AUTH_FAILED,
    CONNECTION_FAILED,
    NOT_FOUND,
    TIMEOUT,
    UPSTREAM_ERROR,
    ToolError,
)


class AsteriskARIConnector:
    def __init__(self, config: ARIConfig, *, timeout_s: float = 4.0) -> None:
        self.config = config
        self.timeout_s = timeout_s

    def _auth_header(self) -> str:
        import os

        user = os.getenv(self.config.username_env)
        passwd = os.getenv(self.config.password_env)
        if not user or not passwd:
            raise ToolError(AUTH_FAILED, "ARI credentials missing from environment")
        token = base64.b64encode(f"{user}:{passwd}".encode("utf-8")).decode("ascii")
        return f"Basic {token}"

    def get(self, path: str) -> dict[str, Any] | list[Any]:
        url = f"{self.config.url.rstrip('/')}/{path.lstrip('/')}"
        req = urllib.request.Request(
            url=url, method="GET", headers={"Authorization": self._auth_header()}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = resp.read().decode("utf-8", errors="replace")
                if not payload.strip():
                    return {}
                return json.loads(payload)
        except TimeoutError as exc:
            raise ToolError(TIMEOUT, "ARI request timed out", {"url": url}) from exc
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ToolError(AUTH_FAILED, "ARI authentication failed") from exc
            if exc.code == 404:
                raise ToolError(
                    NOT_FOUND, "ARI resource not found", {"url": url}
                ) from exc
            raise ToolError(
                UPSTREAM_ERROR, "ARI request failed", {"url": url, "status": exc.code}
            ) from exc
        except urllib.error.URLError as exc:
            raise ToolError(
                CONNECTION_FAILED,
                "ARI connection failed",
                {"url": url, "reason": str(exc.reason)},
            ) from exc
        except json.JSONDecodeError as exc:
            raise ToolError(
                UPSTREAM_ERROR, "ARI returned invalid JSON", {"url": url}
            ) from exc
        except Exception as exc:
            raise ToolError(
                UPSTREAM_ERROR, "ARI request failed", {"url": url, "reason": str(exc)}
            ) from exc

    def health(self) -> dict[str, Any]:
        started = time.monotonic()
        payload = self.get("asterisk/info")
        return {
            "ok": True,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "raw": payload,
        }

    def close(self) -> None:
        return None
