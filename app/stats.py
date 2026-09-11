import threading
from datetime import datetime
from typing import Callable

WINDOW_MINUTES = 10
EVENT_TYPES = ("cycle_complete", "metal_detected")


def _minute_key(now: datetime) -> int:
    """Minute-truncated wall-clock bucket key (minutes since epoch, local)."""
    return int(now.timestamp()) // 60


def _minute_label(key: int) -> str:
    return datetime.fromtimestamp(key * 60).strftime("%H:%M")


class MinuteCounter:
    """In-process per-minute event counts over a rolling wall-clock window.

    Buckets are keyed by the current local minute; minutes with no events are
    zero-filled in `snapshot`. All methods are thread-safe (events arrive on
    poller/MQTT threads, snapshots on request-handler threads).
    """

    def __init__(self, window_minutes: int = WINDOW_MINUTES,
                 clock: Callable[[], datetime] = datetime.now):
        if window_minutes < 1:
            raise ValueError("window_minutes must be >= 1")
        self._window = window_minutes
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: dict[int, dict[str, int]] = {}

    def record(self, event_type: str) -> None:
        """Count one event into the current minute's bucket."""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type '{event_type}'")
        key = _minute_key(self._clock())
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = dict.fromkeys(EVENT_TYPES, 0)
                self._buckets[key] = bucket
                self._evict_locked(key)
            bucket[event_type] += 1

    def snapshot(self, window_minutes: int = WINDOW_MINUTES) -> list[dict]:
        """Per-minute points (oldest first) covering the trailing window."""
        if window_minutes < 1:
            raise ValueError("window_minutes must be >= 1")
        now_key = _minute_key(self._clock())
        with self._lock:
            return [
                self._point_locked(now_key - offset)
                for offset in range(window_minutes - 1, -1, -1)
            ]

    def reset(self) -> None:
        """Clear all buckets (count window restarts from empty)."""
        with self._lock:
            self._buckets.clear()

    def _evict_locked(self, now_key: int) -> None:
        for stale in [k for k in self._buckets if now_key - k >= self._window]:
            self._buckets.pop(stale, None)

    def _point_locked(self, key: int) -> dict:
        bucket = self._buckets.get(key) or dict.fromkeys(EVENT_TYPES, 0)
        return {
            "minute": _minute_label(key),
            "cycles": bucket["cycle_complete"],
            "metal": bucket["metal_detected"],
        }
