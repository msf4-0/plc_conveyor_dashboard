"""Dashboard session-gate tests: login/logout endpoints and /api/* gating."""

from fastapi.testclient import TestClient

import app.main as main
from app.auth import COOKIE_NAME


def _client() -> TestClient:
    return TestClient(main.app)  # fresh client: no cookie


def test_gated_route_401_without_login():
    res = _client().get("/api/state")
    assert res.status_code == 401
    assert res.json() == {"detail": "not logged in"}


def test_wrong_password_401_no_cookie():
    client = _client()
    res = client.post("/api/login", json={"password": "wrong"})
    assert res.status_code == 401
    assert COOKIE_NAME not in client.cookies


def test_login_sets_signed_cookie_and_gated_routes_pass():
    client = _client()
    res = client.post("/api/login", json={"password": main.config.dashboard_password})
    assert res.status_code == 200
    cookie = res.headers["set-cookie"]
    assert "httponly" in cookie.lower() and "samesite=lax" in cookie.lower()
    assert "path=/" in cookie.lower() and "max-age=43200" in cookie.lower()
    assert client.get("/api/state").status_code == 200
    assert client.get("/api/stats").status_code == 200


def test_tampered_cookie_rejected():
    client = _client()
    client.post("/api/login", json={"password": main.config.dashboard_password})
    client.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME) + "x")
    assert client.get("/api/state").status_code == 401


def test_expired_cookie_rejected(monkeypatch):
    import time as time_mod

    client = _client()
    client.post("/api/login", json={"password": main.config.dashboard_password})
    real_time = time_mod.time
    monkeypatch.setattr(time_mod, "time", lambda: real_time() + 12 * 3600 + 60)
    assert client.get("/api/state").status_code == 401


def test_logout_clears_session():
    client = _client()
    client.post("/api/login", json={"password": main.config.dashboard_password})
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/state").status_code == 401


def test_page_and_static_reachable_without_login():
    client = _client()
    assert client.get("/").status_code == 200
    assert client.get("/static/index.html").status_code == 200


def test_api_oee_connection_gated_body_holds_db_creds():
    # the OEE connection endpoint carries a DB password in the body: the
    # gate must reject it before FastAPI parses the credentials
    res = _client().post(
        "/api/oee/connection",
        json={"ip": "1.2.3.4", "port": 5432, "user": "u", "password": "p"},
    )
    assert res.status_code == 401


# -- /mcp bearer token (non-browser MCP clients; no session-cookie fallback) --

MCP_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def test_mcp_missing_token_401():
    res = _client().post("/mcp", json=MCP_INIT, headers=MCP_HEADERS)
    assert res.status_code == 401


def test_mcp_wrong_token_401():
    client = _client()
    res = client.post(
        "/mcp",
        json=MCP_INIT,
        headers={**MCP_HEADERS, "Authorization": "Bearer wrong"},
    )
    assert res.status_code == 401


def test_mcp_session_cookie_not_honored():
    client = _client()
    client.post("/api/login", json={"password": main.config.dashboard_password})
    assert client.post("/mcp", json=MCP_INIT, headers=MCP_HEADERS).status_code == 401


def test_mcp_correct_token_lists_tools(monkeypatch):
    # base_url with a port: the SDK's DNS-rebinding protection allows Host
    # "localhost:<any port>" but not a bare "localhost"; the context manager
    # runs the lifespan (session manager). test_api.py may have swapped in a
    # stub poller without start/stop: keep the lifespan working.
    class _LifecyclePoller:
        source = "direct"
        connection = "test"

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(main, "poller", _LifecyclePoller())
    with TestClient(main.app, base_url="http://localhost:8000") as client:
        res = client.post(
            "/mcp",
            json=MCP_INIT,
            headers={
                **MCP_HEADERS,
                "Authorization": f"Bearer {main.config.mcp_token}",
            },
        )
        assert res.status_code == 200
        # text/event-stream body: find the initialized session, then list tools
        sid = res.headers.get("mcp-session-id")
        assert sid
        res2 = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            headers={
                **MCP_HEADERS,
                "Authorization": f"Bearer {main.config.mcp_token}",
                "Mcp-Session-Id": sid,
            },
        )
        res3 = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={
                **MCP_HEADERS,
                "Authorization": f"Bearer {main.config.mcp_token}",
                "Mcp-Session-Id": sid,
            },
        )
        assert res3.status_code == 200
        assert "get_iq_data" in res3.text and "get_latest_oee" in res3.text
