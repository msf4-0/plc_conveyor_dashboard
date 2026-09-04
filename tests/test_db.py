from datetime import datetime, timedelta, timezone

import pytest

from app.config import load_config
from app.db import ensure_schema, insert_event, per_minute_counts


@pytest.fixture(scope="module")
def dsn():
    cfg = load_config()
    ensure_schema(cfg.database_url)
    return cfg.database_url


def _cleanup(dsn, ids):
    from app.db import connect_db

    if ids:
        with connect_db(dsn) as conn:
            conn.execute("DELETE FROM line_events WHERE id = ANY(%s)", (ids,))
            conn.commit()


def test_round_trip_insert_and_count(dsn):
    ids = []
    try:
        now = datetime.now()  # DB to_char() renders in server-local time
        # events in the current minute and two minutes ago
        import psycopg

        with pytest.raises(psycopg.errors.CheckViolation):
            insert_event(dsn, "bogus_type")
        for _ in range(2):
            ids.append(insert_event(dsn, "cycle_complete"))
        ids.append(insert_event(dsn, "metal_detected"))

        counts = per_minute_counts(dsn, window_minutes=10)
        assert len(counts) == 10
        assert counts[-1]["minute"] == now.strftime("%H:%M")
        assert counts[-1]["cycles"] >= 2
        assert counts[-1]["metal"] >= 1
    finally:
        _cleanup(dsn, ids)


def test_window_includes_zero_minutes(dsn):
    counts = per_minute_counts(dsn, window_minutes=10)
    assert len(counts) == 10
    assert all(set(p) == {"minute", "cycles", "metal"} for p in counts)


def test_timestamped_events_persist(dsn):
    ids = []
    try:
        ids.append(insert_event(dsn, "cycle_complete"))
        from app.db import connect_db

        with connect_db(dsn) as conn:
            row = conn.execute(
                "SELECT occurred_at FROM line_events WHERE id = %s", (ids[0],)
            ).fetchone()
        assert row is not None
        assert abs(
            row[0] - datetime.now(timezone.utc)
        ) < timedelta(minutes=1)
    finally:
        _cleanup(dsn, ids)
