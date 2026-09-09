"""Simplified OEE engine: cycle counting, run/stop time accumulation, and
OEE metrics per oee.com methodology — with no line operating state machine.

One instance serves the directly-connected PLC in the standalone recorder.
Recording starts the moment the recorder starts: counting and timing are
never gated by line state. Run Time accrues while the PLC is connected and
Stop Time while the red tower light P1 is on. Sources feed one snapshot per
successful poll via on_snapshot(); comms failures call on_disconnect().
The next snapshot after a disconnect only re-baselines (no time or counts
are credited across the gap).
"""

import threading

from app.config import (
    IDEAL_CYCLE_TIME_DEFAULT_S,
    IDEAL_CYCLE_TIME_MAX_S,
    IDEAL_CYCLE_TIME_MIN_S,
)


def _validated_ideal(seconds: float) -> float:
    seconds = float(seconds)
    if not (IDEAL_CYCLE_TIME_MIN_S <= seconds <= IDEAL_CYCLE_TIME_MAX_S):
        raise ValueError(
            "ideal cycle time must be between "
            f"{IDEAL_CYCLE_TIME_MIN_S} and {IDEAL_CYCLE_TIME_MAX_S} seconds"
        )
    return seconds


class OeeEngine:
    """Thread-safe accumulator for one line's OEE figures."""

    def __init__(
        self, ideal_cycle_time_s: float = IDEAL_CYCLE_TIME_DEFAULT_S
    ):
        self._lock = threading.Lock()
        self._ideal_ct = _validated_ideal(ideal_cycle_time_s)
        self._baseline = True     # next snapshot only re-baselines
        self._last_ts: float | None = None
        self._prev: dict[str, bool] | None = None
        self._good = 0
        self._bad = 0             # classified counts only
        self._in_flight = 0
        self._total = 0
        self._open_cycle: dict[str, bool] | None = None
        self._run_s = 0.0
        self._stop_s = 0.0

    # -- ingestion -----------------------------------------------------------

    def on_snapshot(self, raw: dict[str, bool], now: float) -> None:
        """Feed one poll snapshot (monotonic `now`)."""
        with self._lock:
            if self._baseline:
                self._rebaseline_locked(raw, now)
                return
            delta = max(
                0.0, now - (self._last_ts if self._last_ts is not None else now)
            )
            self._last_ts = now

            # credit the interval to the signals that held during it: the
            # interval counts as run time, and as stop time when P1 (red
            # light) was on for it
            self._run_s += delta
            if self._prev.get("P1", False):
                self._stop_s += delta
            self._count_locked(raw)
            self._prev = dict(raw)

    def on_disconnect(self) -> None:
        """Pause accumulation; the next snapshot re-baselines the engine."""
        with self._lock:
            self._baseline = True

    # -- baseline ------------------------------------------------------------

    def _rebaseline_locked(self, raw: dict[str, bool], now: float) -> None:
        """First snapshot after startup/reconnect: no time or counts for the
        gap; edge detection starts from this snapshot's levels."""
        self._baseline = False
        self._last_ts = now
        self._prev = dict(raw)

    # -- cycle counting ------------------------------------------------------

    def _count_locked(self, raw: dict[str, bool]) -> None:
        prev = self._prev or raw
        b3_rising = raw["B3"] and not prev["B3"]
        b1_rising = raw["B1"] and not prev["B1"]

        if b3_rising:
            if self._open_cycle is not None:
                # new part entered before the previous reached B1: the old
                # cycle cannot be good, force-classify it as bad
                self._bad += 1
                self._in_flight -= 1
            self._total += 1
            self._in_flight += 1
            self._open_cycle = {
                "b2": bool(raw["B2"]),
                "b4": bool(raw["B4"]),
            }

        if self._open_cycle is not None:
            self._open_cycle["b2"] = self._open_cycle["b2"] or bool(raw["B2"])
            self._open_cycle["b4"] = self._open_cycle["b4"] or bool(raw["B4"])
            if b1_rising:
                if self._open_cycle["b2"] and not self._open_cycle["b4"]:
                    self._good += 1
                else:
                    self._bad += 1
                self._in_flight -= 1
                self._open_cycle = None

    # -- reporting -----------------------------------------------------------

    def metrics(self) -> dict:
        with self._lock:
            total = self._total
            good = self._good
            classified_bad = self._bad
            in_flight = self._in_flight
            run = self._run_s
            stop = self._stop_s
            ideal = self._ideal_ct
        bad = classified_bad + in_flight
        availability = performance = quality = oee = None
        if run > 0:
            availability = (run - stop) / run * 100.0
            performance = (ideal * total) / run * 100.0
            if total > 0:
                quality = good / total * 100.0
                oee = availability * performance * quality / (100.0 * 100.0)
        return {
            "total": total,
            "good": good,
            "bad": bad,
            "in_flight": in_flight,
            "run_time_s": run,
            "stop_time_s": stop,
            "ideal_cycle_time_s": ideal,
            "availability": availability,
            "performance": performance,
            "quality": quality,
            "oee": oee,
        }
