"""Recorder loop scenarios (specs/oee-recording: "Standalone recorder process",
"History persistence to the oee database", "Pause on disconnect")."""

import pytest

from app.oee import OeeEngine
from app.recorder import OeeRecorder
from app.tags import TAGS, Area


def encode_state(state: dict[str, bool]) -> tuple[bytes, bytes]:
    """Encode a value dict into (inputs, outputs) process-image bytes."""
    inputs = bytearray(2)
    outputs = bytearray(2)
    for name, value in state.items():
        tag = TAGS[name]
        data = inputs if tag.area is Area.INPUT else outputs
        if value:
            data[tag.byte] |= 1 << tag.bit
    return bytes(inputs), bytes(outputs)


class ScriptedReader:
    """Fake PLC: pops scripted snapshots per read; can simulate comms failure."""

    def __init__(self, states):
        self.states = [encode_state(s) for s in states]
        self.fail = False
        self.connect_count = 0

    def connect(self):
        self.connect_count += 1

    def read(self):
        if self.fail or not self.states:
            raise ConnectionError("comms lost")
        return self.states.pop(0)

    def close(self):
        pass


def make_recorder(engine, states, clock, inserts, insert_row=None):
    reader = ScriptedReader(states)
    rec = OeeRecorder(
        reader=reader,
        dsn="postgresql://test/oee",
        poll_interval_s=0.5,
        write_interval_s=1.0,
        engine=engine,
        insert_row=insert_row or (lambda dsn, a, p, q, o: inserts.append((a, p, q, o))),
        now_fn=lambda: clock["t"],
    )
    return rec, reader


def test_rows_written_at_write_interval():
    """One row per write interval with the engine's current figures."""
    engine = OeeEngine(ideal_cycle_time_s=5.0)
    inserts = []
    clock = {"t": 0.0}
    rec, _ = make_recorder(engine, [{}, {"B3": True}], clock, inserts)

    clock["t"] = 0.0
    assert rec.poll_once() is True               # baseline
    clock["t"] = 0.5
    assert rec.poll_once() is True               # B3 rising: total = 1
    assert rec.maybe_write() is True             # first row lands right away
    availability, performance, quality, oee = inserts[0]
    assert availability == pytest.approx(100.0)  # no P1 in the held interval
    assert performance == pytest.approx(5.0 * 1 / 0.5 * 100.0)
    assert quality == 0.0                        # cycle still open: in-flight = bad
    assert oee == 0.0

    clock["t"] = 0.8
    assert rec.maybe_write() is False            # write interval not elapsed
    clock["t"] = 1.5
    assert rec.maybe_write() is True             # 1 s since the last write
    assert len(inserts) == 2


def test_null_row_before_run_time():
    """Run time zero -> the persisted figures are NULL, not zeros."""
    engine = OeeEngine()
    inserts = []
    clock = {"t": 0.0}
    rec, _ = make_recorder(engine, [{}], clock, inserts)
    clock["t"] = 0.0
    rec.poll_once()                              # baseline only: run = 0
    clock["t"] = 2.0
    assert rec.maybe_write() is True
    assert inserts == [(None, None, None, None)]


def test_no_rows_while_disconnected():
    """The disconnected period is not filled with frozen duplicate rows."""
    engine = OeeEngine()
    inserts = []
    clock = {"t": 0.0}
    rec, reader = make_recorder(engine, [{}], clock, inserts)

    clock["t"] = 0.0
    assert rec.poll_once() is True
    clock["t"] = 0.5
    reader.fail = True                           # comms lost
    assert rec.poll_once() is False
    clock["t"] = 10.0
    assert rec.maybe_write() is False
    assert inserts == []
    # engine paused: the outage is not credited
    assert engine.metrics()["run_time_s"] == 0.0


def test_recorder_survives_db_failure():
    """A failed insert is logged and recording continues."""
    engine = OeeEngine()
    inserts = []
    clock = {"t": 0.0}
    calls = {"n": 0}

    def flaky_insert(dsn, a, p, q, o):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db down")
        inserts.append((a, p, q, o))

    rec, _ = make_recorder(engine, [{}], clock, inserts, insert_row=flaky_insert)
    clock["t"] = 0.0
    assert rec.poll_once() is True
    clock["t"] = 2.0
    assert rec.maybe_write() is False            # db down: logged, no crash
    clock["t"] = 4.0
    assert rec.maybe_write() is True             # db back: row lands
    assert inserts == [(None, None, None, None)]


def test_reconnect_rebaselines_without_phantom_counts():
    engine = OeeEngine()
    inserts = []
    clock = {"t": 0.0}
    # B3 held on across the outage: baseline on resume, no phantom cycle
    rec, reader = make_recorder(
        engine, [{}, {"B3": True}, {"B3": True}, {"B3": True}], clock, inserts
    )

    clock["t"] = 0.0
    rec.poll_once()                              # baseline
    clock["t"] = 0.5
    rec.poll_once()                              # B3 rising: total = 1
    assert engine.metrics()["total"] == 1
    clock["t"] = 1.0
    reader.fail = True
    assert rec.poll_once() is False              # outage (B3 still on)
    clock["t"] = 100.0
    reader.fail = False
    assert rec.poll_once() is True               # resume: B3 on, baseline only
    assert engine.metrics()["total"] == 1        # no phantom count
    clock["t"] = 100.5
    rec.poll_once()                              # B3 stays on: no rising edge
    assert engine.metrics()["total"] == 1


def test_recorder_reconnects_after_failure():
    engine = OeeEngine()
    clock = {"t": 0.0}
    rec, reader = make_recorder(engine, [{}, {}, {}], clock, [])
    clock["t"] = 0.0
    assert rec.poll_once() is True
    reader.fail = True
    assert rec.poll_once() is False
    reader.fail = False
    clock["t"] = 1.0
    assert rec.poll_once() is True               # reconnected
    assert reader.connect_count >= 2
