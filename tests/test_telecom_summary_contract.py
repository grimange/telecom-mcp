from __future__ import annotations

from types import SimpleNamespace

from telecom_mcp.tools import telecom


def test_summary_asterisk_sources_use_active_channels() -> None:
    class _Ctx:
        settings = SimpleNamespace(
            get_target=lambda _pbx_id: SimpleNamespace(type="asterisk", id="pbx-1")
        )

        def call_tool_internal(self, tool_name: str, _args: dict[str, object]):
            if tool_name == "asterisk.health":
                return {"data": {"asterisk_version": "22.5.2"}}
            if tool_name == "asterisk.active_channels":
                return {"data": {"channels": []}}
            if tool_name == "asterisk.pjsip_show_endpoints":
                return {"data": {"items": []}}
            raise AssertionError(f"unexpected tool call: {tool_name}")

    _target, data = telecom.summary(_Ctx(), {"pbx_id": "pbx-1"})
    assert data["data_quality"]["sources"] == [
        "asterisk.health",
        "asterisk.active_channels",
    ]
