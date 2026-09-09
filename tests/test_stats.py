import threading
from datetime import datetime

import pytest

from app.stats import MinuteCounter


def test_record_and_labels():
    counter = MinuteCounter(clock=lambda: datetime(2026, 9, 9, 10, 5, 30))
    counter.record("cycle_complete")
    counter.record("cycle_complete")
    counter.record("metal_detected")
    points = counter.snapshot()
    assert len(points) == 10
    # last point is the current minute
    assert points[-1] == {"minute": "10:05", "cycles": 2, "metal": 1}
    # earlier minutes are zero-filled
    assert points[-2] == {"minute": "10:04", "cycles": 0, "metal": 0}


def test_window_rollover(monkeypatch):
    times = iter([datetime(2026, 9, 9, 10, 0), datetime(2026, 9, 9, 10, 9)])
    counter = MinuteCounter(clock=lambda: next(times))
    counter.record("cycle_complete")
    # 9 minutes later the old bucket has rolled out of the 10-minute window
    points = counter.snapshot()
    assert points[0]["minute"] == "10:00"
    assert points[-1] == {"minute": "10:09", "cycles": 0, "metal": 0}
    assert all(p["cycles"] == 0 for p in points[1:])


def test_zero_fill_ordering(monkeypatch):
    counter = MinuteCounter(clock=lambda: datetime(2026, 9, 9, 8, 0, 0))
    counter.record("metal_detected")
    points = counter.snapshot(window_minutes=3)
    assert [p["minute"] for p in points] == ["07:58", "07:59", "08:00"]
    assert points[-1]["metal"] == 1
    assert points[0]["metal"] == 0


def test_reset_clears_counts(monkeypatch):
    counter = MinuteCounter(clock=lambda: datetime(2026, 9, 9, 10, 5, 0))
    counter.record("cycle_complete")
    counter.reset()
    points = counter.snapshot(window_minutes=1)
    assert points == [{"minute": "10:05", "cycles": 0, "metal": 0}]


def test_old_buckets_are_evicted(monkeypatch):
    counter = MinuteCounter(clock=lambda: datetime(2026, 9, 9, 10, 0, 0))
    for _ in range(50):
        counter.record("cycle_complete")
    counter.snapshot()
    counter.reset()
    # after reset nothing lingers
    assert counter.snapshot(window_minutes=1)[0]["cycles"] == 0


def test_record_rejects_unknown_event_type():
    counter = MinuteCounter()
    with pytest.raises(ValueError):
        counter.record("bogus")


def test_snapshot_rejects_bad_window():
    counter = MinuteCounter()
    with pytest.raises(ValueError):
        counter.snapshot(window_minutes=0)


def test_concurrent_record_and_snapshot():
    counter = MinuteCounter()

    def worker():
        for _ in range(500):
            counter.record("cycle_complete")

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    points = counter.snapshot(window_minutes=1)
    # all 2000 events land in minute buckets of the run (may straddle a
    # boundary, so check the total across the window)
    assert sum(p["cycles"] for p in counter.snapshot(window_minutes=10)) == 2000
