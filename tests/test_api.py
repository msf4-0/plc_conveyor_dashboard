from fastapi.testclient import TestClient

import app.main as main
from app.config import load_config
from app.db import connect_db, insert_event, per_minute_counts


class StubPoller:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    def snapshot(self):
        return self._snapshot


CLIENT = TestClient(main.app)  # lifespan (real poller) not started in tests


def test_api_state_shape_and_polarity():
    snapshot = {
        "connected": True,
        "stale": False,
        "connecting": False,
        "server_time": "2026-09-04T06:00:00+00:00",
        "last_update": "2026-09-04T06:00:00+00:00",
        "values": {
            "lights": {"red": False, "yellow": False, "green": True},
            "buttons": {
                "e_stop": {"name": "ESO", "pressed": False},
                "stop": {"name": "S1", "pressed": False},
                "start": {"name": "S2", "pressed": True},
                "reset": {"name": "S3", "pressed": False},
            },
            "conveyor": {"running": True},
            "sensors": {
                "b1": {"name": "B1", "detecting": False},
                "b2": {"name": "B2", "detecting": False},
                "b3": {"name": "B3", "detecting": True},
                "metal_detector": {"name": "B4", "detecting": False},
            },
        },
        "line_ip": "192.168.5.3",
        "source": "direct",
        "lines": {},
    }
    main.poller = StubPoller(snapshot)
    res = CLIENT.get("/api/state")
    assert res.status_code == 200
    body = res.json()
    assert body["connected"] is True and body["stale"] is False
    assert body["values"]["lights"]["green"] is True
    assert body["values"]["buttons"]["stop"]["pressed"] is False
    assert body["values"]["conveyor"]["running"] is True
    assert body["values"]["sensors"]["metal_detector"]["name"] == "B4"


def test_api_state_reports_stale():
    main.poller = StubPoller(
        {"connected": False, "stale": True, "connecting": True, "server_time": "t",
         "last_update": "t", "values": None, "line_ip": "x", "source": "direct", "lines": {}}
    )
    body = CLIENT.get("/api/state").json()
    assert body["stale"] is True and body["values"] is None


class SwitchableStub:
    def __init__(self):
        self.switched_to = None
        self.switched_source = None
        self.source = "mqtt"

    def snapshot(self):
        return {"connected": False, "stale": True, "connecting": True, "server_time": "t",
                "last_update": None, "values": None, "line_ip": self.switched_to,
                "source": self.source, "lines": {"10.0.0.1": "h1:1883", "10.0.0.2": "h2:1883"}}

    def set_line(self, line_ip):
        self.switched_to = line_ip

    def switch(self, source_name, line_ip=None):
        self.switched_source = (source_name, line_ip)
        self.source = source_name
        return self.snapshot()

    @property
    def line_ip(self):
        return self.switched_to


def test_api_line_select_in_mqtt_mode(monkeypatch):
    stub = SwitchableStub()
    fake_config = type("C", (), {"data_source": "mqtt", "lines": {"10.0.0.1": ("h1", 1883), "10.0.0.2": ("h2", 1883)}})()
    monkeypatch.setattr(main, "config", fake_config)
    monkeypatch.setattr(main, "poller", stub)
    res = CLIENT.post("/api/line", json={"line_ip": "10.0.0.2"})
    assert res.status_code == 200
    assert stub.switched_to == "10.0.0.2"
    assert CLIENT.get("/api/state").json()["lines"] != {}


def test_api_line_unknown_line_404(monkeypatch):
    stub = SwitchableStub()
    fake_config = type("C", (), {"data_source": "mqtt", "lines": {"10.0.0.1": ("h1", 1883)}})()
    monkeypatch.setattr(main, "config", fake_config)
    monkeypatch.setattr(main, "poller", stub)
    res = CLIENT.post("/api/line", json={"line_ip": "10.9.9.9"})
    assert res.status_code == 404


def test_api_line_rejected_in_direct_mode(monkeypatch):
    class DirectStub:
        source = "direct"

        def snapshot(self):
            return {"connected": True, "stale": False, "connecting": False, "server_time": "t",
                    "last_update": "t", "values": None, "line_ip": "p", "source": "direct", "lines": {}}

    fake_config = type("C", (), {"data_source": "direct", "lines": None})()
    monkeypatch.setattr(main, "config", fake_config)
    monkeypatch.setattr(main, "poller", DirectStub())
    res = CLIENT.post("/api/line", json={"line_ip": "10.0.0.2"})
    assert res.status_code == 400


def test_api_source_switch(monkeypatch):
    stub = SwitchableStub()
    fake_config = type("C", (), {"data_source": "direct", "lines": {"10.0.0.1": ("h1", 1883), "10.0.0.2": ("h2", 1883)}})()
    monkeypatch.setattr(main, "config", fake_config)
    monkeypatch.setattr(main, "poller", stub)
    res = CLIENT.post("/api/source", json={"source": "mqtt", "line_ip": "10.0.0.2"})
    assert res.status_code == 200
    assert stub.switched_source == ("mqtt", "10.0.0.2")
    # switch back without a line: direct ignores line_ip
    res = CLIENT.post("/api/source", json={"source": "direct"})
    assert res.status_code == 200
    assert stub.switched_source == ("direct", None)


def test_api_source_invalid_source_400(monkeypatch):
    stub = SwitchableStub()
    fake_config = type("C", (), {"data_source": "direct", "lines": None})()
    monkeypatch.setattr(main, "config", fake_config)
    monkeypatch.setattr(main, "poller", stub)
    res = CLIENT.post("/api/source", json={"source": "modbus"})
    assert res.status_code == 400
    assert stub.switched_source is None


def test_api_source_unknown_line_404(monkeypatch):
    stub = SwitchableStub()
    fake_config = type("C", (), {"data_source": "direct", "lines": {"10.0.0.1": ("h1", 1883)}})()
    monkeypatch.setattr(main, "config", fake_config)
    monkeypatch.setattr(main, "poller", stub)
    res = CLIENT.post("/api/source", json={"source": "mqtt", "line_ip": "10.9.9.9"})
    assert res.status_code == 404


def test_api_stats_matches_db(dsn=None):
    dsn_url = load_config().database_url
    line_ip = main.config.plc_ip  # direct-mode poller tags events with the PLC IP
    event_id = insert_event(dsn_url, "cycle_complete", line_ip=line_ip)
    try:
        body = CLIENT.get(f"/api/stats?line_ip={line_ip}").json()
        assert body["window_minutes"] == 10
        assert body["line_ip"] == line_ip
        assert len(body["points"]) == 10
        current = body["points"][-1]
        db_counts = per_minute_counts(dsn_url, line_ip=line_ip)
        assert current["cycles"] == db_counts[-1]["cycles"] >= 1
        assert set(body["points"][0]) == {"minute", "cycles", "metal"}
    finally:
        with connect_db(dsn_url) as conn:
            conn.execute("DELETE FROM line_events WHERE id = %s", (event_id,))
            conn.commit()
