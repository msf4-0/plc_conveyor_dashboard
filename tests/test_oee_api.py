"""API-level OEE tests: database-backed /api/oee* endpoints (design D5/D6)."""

import pytest
from fastapi.testclient import TestClient

import app.main as main

CLIENT = TestClient(main.app)

EMPTY_ROW = {
    "timestamp": None,
    "availability": None,
    "performance": None,
    "quality": None,
    "oee": None,
}


@pytest.fixture(autouse=True)
def reset_oee_conn():
    yield
    main._oee_conn.update(dsn=None, ip=None, port=None)


def connect_ok(monkeypatch, ip="10.1.2.3", port=5432, user="u", password="p"):
    monkeypatch.setattr(main, "test_oee_connection", lambda dsn: None)
    res = CLIENT.post(
        "/api/oee/connection",
        json={"ip": ip, "port": port, "user": user, "password": password},
    )
    assert res.status_code == 200


def test_not_connected_payload():
    body = CLIENT.get("/api/oee").json()
    assert body["connected"] is False
    assert body["error"] == "not connected to an OEE database"
    for key in ("timestamp", "availability", "performance", "quality", "oee"):
        assert body[key] is None


def test_connect_success_stores_dsn(monkeypatch):
    monkeypatch.setattr(main, "test_oee_connection", lambda dsn: None)
    res = CLIENT.post(
        "/api/oee/connection",
        json={"ip": "10.1.2.3", "port": 5432, "user": "u", "password": "p"},
    )
    assert res.status_code == 200
    assert res.json() == {"connected": True, "ip": "10.1.2.3", "port": 5432}
    assert main._oee_conn["dsn"] == "postgresql://u:p@10.1.2.3:5432/oee"


def test_connect_password_special_characters_quoted(monkeypatch):
    seen = {}

    def fake_test(dsn):
        seen["dsn"] = dsn

    monkeypatch.setattr(main, "test_oee_connection", fake_test)
    res = CLIENT.post(
        "/api/oee/connection",
        json={"ip": "10.1.2.3", "port": 5432, "user": "us:er", "password": "p@ss/w rd"},
    )
    assert res.status_code == 200
    assert seen["dsn"] == "postgresql://us%3Aer:p%40ss%2Fw%20rd@10.1.2.3:5432/oee"
    assert main._oee_conn["dsn"] == seen["dsn"]


def test_connect_failure_returns_error_and_keeps_previous(monkeypatch):
    connect_ok(monkeypatch, ip="10.0.0.1")
    previous_dsn = main._oee_conn["dsn"]

    def fail(dsn):
        raise RuntimeError("no route to host")

    monkeypatch.setattr(main, "test_oee_connection", fail)
    res = CLIENT.post(
        "/api/oee/connection",
        json={"ip": "10.9.9.9", "port": 5432, "user": "u", "password": "p"},
    )
    assert res.status_code == 502
    assert "10.9.9.9" in res.json()["detail"]
    # previous connection state untouched
    assert main._oee_conn["dsn"] == previous_dsn
    assert main._oee_conn["ip"] == "10.0.0.1"


def test_latest_row_payload(monkeypatch):
    connect_ok(monkeypatch)

    def fake_latest(dsn):
        assert dsn == main._oee_conn["dsn"]
        return {
            "timestamp": "2026-09-08T10:00:00+08:00",
            "availability": 91.0,
            "performance": 87.0,
            "quality": 98.0,
            "oee": 78.0,
        }

    monkeypatch.setattr(main, "latest_oee_row", fake_latest)
    body = CLIENT.get("/api/oee").json()
    assert body["connected"] is True
    assert body["error"] is None
    assert body["oee"] == pytest.approx(78.0)
    assert body["availability"] == pytest.approx(91.0)


def test_latest_row_unreachable_db(monkeypatch):
    connect_ok(monkeypatch)

    def raise_(dsn):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(main, "latest_oee_row", raise_)
    body = CLIENT.get("/api/oee").json()
    assert body["connected"] is False
    assert body["error"] == "OEE database unreachable"
    for key in EMPTY_ROW:
        assert body[key] is None


def test_latest_row_empty_table(monkeypatch):
    connect_ok(monkeypatch)
    monkeypatch.setattr(main, "latest_oee_row", lambda dsn: None)
    body = CLIENT.get("/api/oee").json()
    assert body["connected"] is True
    assert body["error"] == "no OEE data recorded yet"
    for key in EMPTY_ROW:
        assert body[key] is None


def test_history_points(monkeypatch):
    connect_ok(monkeypatch)
    points = [
        {"timestamp": "2026-09-08T09:59:00+08:00", "availability": 90.0,
         "performance": 80.0, "quality": 99.0, "oee": 71.0},
        {"timestamp": "2026-09-08T10:00:00+08:00", "availability": 91.0,
         "performance": 87.0, "quality": 98.0, "oee": 78.0},
    ]
    seen = {}

    def fake_history(dsn, minutes):
        seen["minutes"] = minutes
        return points

    monkeypatch.setattr(main, "oee_history", fake_history)
    body = CLIENT.get("/api/oee/history?minutes=5").json()
    assert seen["minutes"] == 5
    assert body == {"minutes": 5, "points": points}


def test_history_not_connected_returns_empty_points():
    body = CLIENT.get("/api/oee/history").json()
    assert body == {"minutes": 10, "points": []}


def test_history_invalid_minutes_400():
    assert CLIENT.get("/api/oee/history?minutes=0").status_code == 400
    assert CLIENT.get("/api/oee/history?minutes=2000").status_code == 400
    assert CLIENT.get("/api/oee/history?minutes=abc").status_code == 422


def test_removed_oee_endpoints_gone():
    assert CLIENT.post("/api/oee/reset").status_code == 404
    assert CLIENT.put(
        "/api/oee/ideal-cycle-time", json={"seconds": 5.0}
    ).status_code == 404


def test_state_has_no_line_state_fields():
    class StubPoller:
        def snapshot(self):
            return {"connected": True, "stale": False, "connecting": False,
                    "server_time": "t", "last_update": "t", "values": None,
                    "line_ip": "192.168.5.3", "source": "direct", "lines": {}}

    main.poller = StubPoller()
    body = CLIENT.get("/api/state").json()
    assert "line_state" not in body
    assert "oee_paused" not in body
