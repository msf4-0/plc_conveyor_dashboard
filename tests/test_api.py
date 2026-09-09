from datetime import datetime

from fastapi.testclient import TestClient

import app.main as main
from app.stats import MinuteCounter


class StubPoller:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    def snapshot(self):
        return self._snapshot

    @property
    def connection(self):
        return self._snapshot.get("broker") or self._snapshot.get("line_ip")


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
         "last_update": "t", "values": None, "line_ip": "x", "source": "direct"}
    )
    body = CLIENT.get("/api/state").json()
    assert body["stale"] is True and body["values"] is None


def test_api_state_mqtt_reports_broker():
    main.poller = StubPoller(
        {"connected": True, "stale": False, "connecting": False, "server_time": "t",
         "last_update": "t", "values": None, "broker": "192.168.0.11:1883", "source": "mqtt"}
    )
    body = CLIENT.get("/api/state").json()
    assert body["broker"] == "192.168.0.11:1883" and body["source"] == "mqtt"


class SwitchableStub:
    def __init__(self):
        self.switched = None
        self.source = "mqtt"

    @property
    def connection(self):
        return "192.168.0.11:1883" if self.source == "mqtt" else "192.168.5.3"

    def snapshot(self):
        return {"connected": False, "stale": True, "connecting": True, "server_time": "t",
                "last_update": None, "values": None, "broker": None, "source": self.source}

    def switch(self, source_name, broker=None):
        self.switched = (source_name, broker)
        self.source = source_name
        return self.snapshot()


def test_api_source_switch_to_mqtt_with_broker(monkeypatch):
    stub = SwitchableStub()
    monkeypatch.setattr(main, "poller", stub)
    res = CLIENT.post("/api/source", json={"source": "mqtt", "broker": "192.168.0.11:1884"})
    assert res.status_code == 200
    assert stub.switched == ("mqtt", ("192.168.0.11", 1884))
    # switch back without a broker: direct ignores it
    res = CLIENT.post("/api/source", json={"source": "direct"})
    assert res.status_code == 200
    assert stub.switched == ("direct", None)


def test_api_source_bare_ip_defaults_to_port_1883(monkeypatch):
    stub = SwitchableStub()
    monkeypatch.setattr(main, "poller", stub)
    res = CLIENT.post("/api/source", json={"source": "mqtt", "broker": "192.168.0.11"})
    assert res.status_code == 200
    assert stub.switched == ("mqtt", ("192.168.0.11", 1883))


def test_api_source_mqtt_without_broker_400(monkeypatch):
    stub = SwitchableStub()
    monkeypatch.setattr(main, "poller", stub)
    res = CLIENT.post("/api/source", json={"source": "mqtt"})
    assert res.status_code == 400
    assert stub.switched is None


def test_api_source_malformed_broker_400(monkeypatch):
    stub = SwitchableStub()
    monkeypatch.setattr(main, "poller", stub)
    for bad in ["", " ", ":", "192.168.0.11:", "192.168.0.11:0",
                "192.168.0.11:70000", "192.168.0.11:abc", ":1883"]:
        res = CLIENT.post("/api/source", json={"source": "mqtt", "broker": bad})
        assert res.status_code == 400, bad
    assert stub.switched is None


def test_api_source_retype_broker_while_in_mqtt(monkeypatch):
    stub = SwitchableStub()
    stub.source = "mqtt"
    monkeypatch.setattr(main, "poller", stub)
    res = CLIENT.post("/api/source", json={"source": "mqtt", "broker": "192.168.0.12:1883"})
    assert res.status_code == 200
    assert stub.switched == ("mqtt", ("192.168.0.12", 1883))


def test_api_source_invalid_source_400(monkeypatch):
    stub = SwitchableStub()
    stub.source = "direct"
    monkeypatch.setattr(main, "poller", stub)
    res = CLIENT.post("/api/source", json={"source": "modbus"})
    assert res.status_code == 400
    assert stub.switched is None


def test_api_line_endpoint_removed():
    res = CLIENT.post("/api/line", json={"line_ip": "10.0.0.2"})
    assert res.status_code in (404, 405)  # route gone (405 from FastAPI route list)


def test_api_stats_from_in_memory_counter(monkeypatch):
    counter = MinuteCounter(clock=lambda: datetime(2026, 9, 9, 10, 5, 0))
    counter.record("cycle_complete")
    counter.record("cycle_complete")
    counter.record("metal_detected")
    monkeypatch.setattr(main, "counter", counter)
    monkeypatch.setattr(main, "poller", SwitchableStub())
    body = CLIENT.get("/api/stats").json()
    assert body["window_minutes"] == 10
    assert body["connection"] == "192.168.0.11:1883"  # stub reports mqtt broker
    assert len(body["points"]) == 10
    assert body["points"][-1] == {"minute": "10:05", "cycles": 2, "metal": 1}
    assert set(body["points"][0]) == {"minute", "cycles", "metal"}


def test_api_stats_counter_reset_empties_window(monkeypatch):
    counter = MinuteCounter(clock=lambda: datetime(2026, 9, 9, 10, 5, 0))
    counter.record("cycle_complete")
    monkeypatch.setattr(main, "counter", counter)
    assert CLIENT.get("/api/stats").json()["points"][-1]["cycles"] == 1
    # a source/broker switch triggers on_connection_change -> counter.reset()
    counter.reset()
    body = CLIENT.get("/api/stats").json()
    assert all(p["cycles"] == 0 and p["metal"] == 0 for p in body["points"])
