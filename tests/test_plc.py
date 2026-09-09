import time

import pytest

from app.plc import PlcPoller


class FakePlcReader:
    """Fake PLC: scriptable input/output bytes; can simulate comms failure."""

    def __init__(self, inputs: bytearray, outputs: bytearray):
        self.inputs = inputs
        self.outputs = outputs
        self.connected = False
        self.fail_reads = False
        self.fail_connect = False
        self.read_count = 0

    def connect(self):
        if self.fail_connect:
            raise ConnectionError("no route to PLC")
        self.connected = True

    def read(self):
        self.read_count += 1
        if self.fail_reads or not self.connected:
            raise ConnectionError("comms lost")
        return bytes(self.inputs), bytes(self.outputs)

    def close(self):
        self.connected = False


def set_bit(data: bytearray, byte: int, bit: int, value: bool):
    if value:
        data[byte] |= 1 << bit
    else:
        data[byte] &= ~(1 << bit)


@pytest.fixture()
def poller_env():
    inputs = bytearray(2)
    outputs = bytearray(2)
    reader = FakePlcReader(inputs, outputs)
    events: list[str] = []
    poller = PlcPoller(reader, poll_interval_ms=20, on_event=events.append)
    yield reader, poller, events
    poller.stop()


def wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_values_refresh_at_poll_rate(poller_env):
    reader, poller, _ = poller_env
    poller.start()
    assert wait_for(lambda: reader.read_count >= 5), (
        f"only {reader.read_count} reads in 5s at 20ms interval"
    )
    snap = poller.snapshot()
    assert snap["connected"] is True and snap["stale"] is False
    assert snap["values"]["conveyor"]["running"] is False


def test_view_reflects_plc_values(poller_env):
    reader, poller, _ = poller_env
    set_bit(reader.inputs, 0, 5, True)  # B3 start sensor
    set_bit(reader.outputs, 0, 6, True)  # P3 green light
    set_bit(reader.outputs, 0, 3, True)  # K1 motor
    set_bit(reader.inputs, 0, 1, False)  # S1 NC pressed (reads LOW)
    poller.start()
    assert wait_for(
        lambda: poller.snapshot()["values"]
        and poller.snapshot()["values"]["conveyor"]["running"]
    )
    values = poller.snapshot()["values"]
    assert values["sensors"]["b3"]["detecting"] is True
    assert values["lights"]["green"] is True
    assert values["buttons"]["stop"]["pressed"] is True
    assert values["buttons"]["start"]["pressed"] is False


def test_stale_freeze_and_reconnect_rebaseline(poller_env):
    reader, poller, events = poller_env
    set_bit(reader.outputs, 0, 6, True)  # P3 ON before outage
    poller.start()
    assert wait_for(lambda: poller.snapshot()["connected"])

    last_update_before = poller.snapshot()["last_update"]
    reader.fail_reads = True  # comms lost
    assert wait_for(lambda: not poller.snapshot()["connected"])
    frozen = poller.snapshot()
    assert frozen["stale"] is True
    assert frozen["values"]["lights"]["green"] is True  # frozen, not blanked
    assert frozen["last_update"] == last_update_before  # values not updated

    # P3 falls while offline; reconnect must re-baseline (no phantom cycle event)
    set_bit(reader.outputs, 0, 6, False)
    reader.fail_reads = False
    assert wait_for(lambda: poller.snapshot()["connected"])
    time.sleep(0.2)
    assert events == []  # no phantom cycle counted on reconnect

    # after baseline, a genuine P3 rising edge is still detected
    set_bit(reader.outputs, 0, 6, True)
    assert wait_for(lambda: "cycle_complete" in events, timeout=5)


def test_events_recorded_on_edges(poller_env):
    reader, poller, events = poller_env
    poller.start()
    assert wait_for(lambda: poller.snapshot()["connected"])
    set_bit(reader.outputs, 0, 6, True)  # P3 rising -> cycle_complete
    assert wait_for(lambda: "cycle_complete" in events)
    set_bit(reader.inputs, 1, 0, True)  # B4 rising -> metal_detected
    assert wait_for(lambda: "metal_detected" in events)
    # no duplicates while signals stay ON
    time.sleep(0.2)
    assert events.count("cycle_complete") == 1
    assert events.count("metal_detected") == 1
