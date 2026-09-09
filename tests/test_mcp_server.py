import asyncio

import app.main as main
from app.mcp_server import create_mcp_server
from app.tags import TAGS

CONNECTED_SNAPSHOT = {
    "connected": True,
    "stale": False,
    "connecting": False,
    "server_time": "2026-09-09T06:00:00+00:00",
    "last_update": "2026-09-09T06:00:00+00:00",
    "values": None,  # UI view irrelevant to the tool
    "raw": {name: (name in ("S2", "P3")) for name in TAGS},
    "line_ip": "192.168.5.3",
    "source": "direct",
}


def _tools(snapshot, dsn=None):
    return create_mcp_server(lambda: snapshot, dsn)._tool_manager


def _call(tm, name, arguments=None):
    return asyncio.run(tm.call_tool(name, arguments or {}))


def test_tool_inventory_is_exactly_two_read_only_tools():
    names = sorted(t.name for t in _tools(CONNECTED_SNAPSHOT).list_tools())
    assert names == ["get_iq_data", "get_latest_oee"]


def test_mcp_streamable_http_endpoint_mounted_with_dashboard_routes():
    paths = {getattr(r, "path", None) for r in main.app.routes}
    for existing in ("/", "/api/state", "/api/stats", "/api/oee"):
        assert existing in paths
    # The MCP sub-app is mounted at "/" *after* the dashboard routes; its
    # single inner route serves the Streamable HTTP endpoint at exactly /mcp.
    from starlette.routing import Mount

    mounts = [r for r in main.app.routes if isinstance(r, Mount) and r.path in ("", "/")]
    assert len(mounts) == 1
    mounted_paths = {getattr(r, "path", None) for r in mounts[0].app.routes}
    assert mounted_paths == {"/mcp"}


def test_get_iq_data_returns_all_14_tags_with_descriptions():
    payload = _call(_tools(CONNECTED_SNAPSHOT), "get_iq_data")
    assert payload["connected"] is True and payload["stale"] is False
    assert payload["source"] == "direct" and payload["connection"] == "192.168.5.3"
    assert set(payload["values"]) == set(TAGS) and len(payload["values"]) == 14
    assert payload["values"]["S2"] is True and payload["values"]["P3"] is True
    assert payload["descriptions"]["B4"] == "Inductive sensor (metal detector)"
    assert "message" not in payload


def test_get_iq_data_disconnected_reports_state_without_values():
    snapshot = {
        "connected": False,
        "stale": True,
        "connecting": False,
        "server_time": "2026-09-09T06:00:00+00:00",
        "last_update": None,
        "values": None,
        "raw": None,
        "line_ip": "192.168.5.3",
        "source": "direct",
    }
    payload = _call(_tools(snapshot), "get_iq_data")
    assert payload["connected"] is False and payload["stale"] is True
    assert payload["values"] is None
    assert "not connected" in payload["message"]


def test_get_iq_data_inactive_mqtt_slot_reports_connecting():
    snapshot = {
        "connected": False,
        "stale": False,
        "connecting": True,
        "server_time": "2026-09-09T06:00:00+00:00",
        "last_update": None,
        "values": None,
        "raw": None,
        "broker": None,
        "source": "mqtt",
    }
    payload = _call(_tools(snapshot), "get_iq_data")
    assert payload["values"] is None and payload["source"] == "mqtt"
    assert "broker address" in payload["message"]


def test_get_iq_data_snapshot_failure_returns_error_payload():
    def boom():
        raise RuntimeError("poller gone")

    payload = _call(create_mcp_server(boom, None)._tool_manager, "get_iq_data")
    assert payload["connected"] is False and payload["values"] is None
    assert "failed to read" in payload["message"]


def test_get_latest_oee_without_dsn_reports_not_configured():
    payload = _call(_tools(CONNECTED_SNAPSHOT, dsn=None), "get_latest_oee")
    assert payload["connected"] is False
    assert "OEE_DATABASE_URL" in payload["error"]
    assert payload["oee"] is None and payload["timestamp"] is None


def test_get_latest_oee_unreachable_database(monkeypatch):
    import app.mcp_server as mod

    def boom(dsn):
        raise ConnectionError("down")

    monkeypatch.setattr(mod, "latest_oee_row", boom)
    payload = _call(_tools(CONNECTED_SNAPSHOT, dsn="postgresql://x/y"), "get_latest_oee")
    assert payload["connected"] is False and payload["error"] == "OEE database unreachable"


def test_get_latest_oee_empty_table(monkeypatch):
    import app.mcp_server as mod

    monkeypatch.setattr(mod, "latest_oee_row", lambda dsn: None)
    payload = _call(_tools(CONNECTED_SNAPSHOT, dsn="postgresql://x/y"), "get_latest_oee")
    assert payload["connected"] is True
    assert payload["error"] == "no OEE data recorded yet"
    assert payload["oee"] is None


def test_get_latest_oee_returns_latest_row(monkeypatch):
    import app.mcp_server as mod

    row = {
        "timestamp": "2026-09-09T06:00:00+00:00",
        "availability": 95.0,
        "performance": 80.0,
        "quality": 100.0,
        "oee": 76.0,
    }
    seen = {}
    def fake(dsn):
        seen["dsn"] = dsn
        return row

    monkeypatch.setattr(mod, "latest_oee_row", fake)
    payload = _call(_tools(CONNECTED_SNAPSHOT, dsn="postgresql://x/y"), "get_latest_oee")
    assert seen["dsn"] == "postgresql://x/y"
    assert payload == {"connected": True, "error": None, **row}
