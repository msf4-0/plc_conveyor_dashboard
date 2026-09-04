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
        {"connected": False, "stale": True, "server_time": "t", "last_update": "t", "values": None}
    )
    body = CLIENT.get("/api/state").json()
    assert body["stale"] is True and body["values"] is None


def test_api_stats_matches_db(dsn=None):
    dsn_url = load_config().database_url
    event_id = insert_event(dsn_url, "cycle_complete")
    try:
        body = CLIENT.get("/api/stats").json()
        assert body["window_minutes"] == 10
        assert len(body["points"]) == 10
        current = body["points"][-1]
        db_counts = per_minute_counts(dsn_url)
        assert current["cycles"] == db_counts[-1]["cycles"] >= 1
        assert set(body["points"][0]) == {"minute", "cycles", "metal"}
    finally:
        with connect_db(dsn_url) as conn:
            conn.execute("DELETE FROM line_events WHERE id = %s", (event_id,))
            conn.commit()
