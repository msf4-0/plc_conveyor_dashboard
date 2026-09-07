import time

import pytest

from app.config import Config
from app.source_manager import SourceManager


class FakeSource:
    def __init__(self, name, line_ip="10.0.0.1", lines=None):
        self.name = name
        self.started = False
        self.stopped = False
        self._snapshot = {
            "connected": True, "stale": False, "connecting": False,
            "server_time": "t", "last_update": "t", "values": None,
            "line_ip": line_ip, "source": name, "lines": lines or {},
        }
        self.lines_set_to = None
        self.fail_start = False

    def start(self):
        if self.fail_start:
            raise RuntimeError("start failed")
        self.started = True

    def stop(self):
        self.stopped = True

    def snapshot(self):
        return self._snapshot

    def set_line(self, line_ip):
        self.lines_set_to = line_ip

    @property
    def line_ip(self):
        return self._snapshot["line_ip"]

    @property
    def lines(self):
        return self._snapshot["lines"]


def make_config(**overrides):
    kwargs = dict(
        plc_ip="192.168.5.3", plc_rack=0, plc_slot=1, poll_interval_ms=500,
        database_url="u", host="h", port=1, data_source="direct",
        mqtt_broker_host="127.0.0.1", mqtt_broker_port=1883,
        lines={"10.0.0.1": ("h1", 1883), "10.0.0.2": ("h2", 1883)},
    )
    kwargs.update(overrides)
    return Config(**kwargs)


class FakeFactory:
    """Records build calls; hands out scripted fake sources."""

    def __init__(self, sources=None):
        self.calls = []
        self.sources = list(sources or [])

    def __call__(self, config, name, line_ip=None):
        self.calls.append((name, line_ip))
        if self.sources:
            src = self.sources.pop(0)
            src.name = name
            if line_ip:
                src._snapshot["line_ip"] = line_ip
            return src
        src = FakeSource(name)
        if line_ip:
            src._snapshot["line_ip"] = line_ip
        return src


def make_manager(factory, initial="direct"):
    return SourceManager(make_config(), initial_source=initial, factory=factory)


def test_delegation_and_properties():
    factory = FakeFactory()
    mgr = make_manager(factory, initial="direct")
    mgr.start()
    mgr.stop()
    assert mgr.snapshot()["source"] == "direct"
    assert mgr.source == "direct"
    assert mgr.line_ip == "10.0.0.1"


def test_unknown_initial_source_rejected():
    with pytest.raises(ValueError):
        make_manager(FakeFactory(), initial="modbus")


def test_build_source_unknown_name_raises():
    from app.source_manager import build_source

    with pytest.raises(ValueError):
        build_source(make_config(), "modbus")


def test_build_source_uses_registry_endpoint_for_registered_line():
    from app.source_manager import build_source

    src = build_source(make_config(), "mqtt", line_ip="10.0.0.1")
    assert src._broker == ("h1", 1883)
    assert src.line_ip == "10.0.0.1"


def test_build_source_falls_back_to_configured_broker_for_unregistered_line():
    from app.source_manager import build_source

    cfg = make_config(mqtt_broker_host="192.0.2.9", mqtt_broker_port=1999)
    src = build_source(cfg, "mqtt", line_ip="10.9.9.9")
    assert src._broker == ("192.0.2.9", 1999)


def test_build_source_defaults_to_first_registry_line():
    from app.source_manager import build_source

    src = build_source(make_config(), "mqtt")
    assert src._broker == ("h1", 1883)
    assert src.line_ip == "10.0.0.1"


def test_switch_swaps_sources_and_stops_old():
    old, new = FakeSource("direct"), FakeSource("mqtt")
    factory = FakeFactory(sources=[old, new])
    mgr = make_manager(factory, initial="direct")
    mgr.switch("mqtt", line_ip="10.0.0.2")
    assert old.stopped is True and new.started is True
    assert mgr.source == "mqtt"
    assert mgr.line_ip == "10.0.0.2"
    assert factory.calls == [("direct", None), ("mqtt", "10.0.0.2")]


def test_switch_to_same_source_is_noop():
    old = FakeSource("direct")
    factory = FakeFactory(sources=[old])
    mgr = make_manager(factory, initial="direct")
    snap = mgr.switch("direct")
    assert old.stopped is False
    assert snap is old._snapshot
    assert len(factory.calls) == 1  # no new build


def test_switch_build_failure_keeps_old():
    class ExplodingFactory:
        def __init__(self, old):
            self.old = old

        def __call__(self, config, name, line_ip=None):
            if name == "mqtt":
                raise RuntimeError("bad broker config")
            return self.old

    old = FakeSource("direct")
    mgr = SourceManager(make_config(), initial_source="direct", factory=ExplodingFactory(old))
    with pytest.raises(RuntimeError):
        mgr.switch("mqtt")
    assert mgr.source == "direct"
    assert old.stopped is False


def test_switch_start_failure_keeps_old():
    new = FakeSource("mqtt")
    new.fail_start = True
    old = FakeSource("direct")
    factory = FakeFactory(sources=[old, new])
    mgr = make_manager(factory, initial="direct")
    with pytest.raises(RuntimeError):
        mgr.switch("mqtt")
    assert mgr.source == "direct"
    assert old.stopped is False


def test_switch_unknown_line_rejected():
    old = FakeSource("direct")
    factory = FakeFactory(sources=[old])
    mgr = make_manager(factory, initial="direct")
    with pytest.raises(ValueError):
        mgr.switch("mqtt", line_ip="10.9.9.9")
    assert old.stopped is False


def test_set_line_delegates_only_in_mqtt():
    mqtt_src = FakeSource("mqtt")
    factory = FakeFactory(sources=[FakeSource("direct"), mqtt_src])
    mgr = make_manager(factory, initial="direct")
    with pytest.raises(ValueError):
        mgr.set_line("10.0.0.2")
    mgr.switch("mqtt")
    mgr.set_line("10.0.0.2")
    assert mqtt_src.lines_set_to == "10.0.0.2"


# ---------------------------------------------------------------------------
# Count integrity across source switches (real sources, fake PLC readers)
# ---------------------------------------------------------------------------

from app.config import load_config
from app.db import connect_db, per_minute_counts
from app.mqtt_source import MqttLineSource
from app.plc import PlcPoller
from app.publisher import LinePublisher


class FakePlc:
    """Fake PLC reader: fixed I/Q bytes, optionally always failing."""

    def __init__(self, fail=False):
        self.inputs = bytearray(2)
        self.outputs = bytearray(2)
        self.fail = fail

    def connect(self):
        if self.fail:
            raise ConnectionError("no route to PLC")

    def read(self):
        if self.fail:
            raise ConnectionError("comms lost")
        return bytes(self.inputs), bytes(self.outputs)

    def close(self):
        pass


def set_bit(data: bytearray, byte: int, bit: int):
    data[byte] |= 1 << bit


def wait_for(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def cleanup_events(dsn, line_ips):
    with connect_db(dsn) as conn:
        conn.execute("DELETE FROM line_events WHERE line_ip = ANY(%s)", (list(line_ips),))
        conn.commit()


def cycles(dsn, line_ip):
    return sum(p["cycles"] for p in per_minute_counts(dsn, line_ip=line_ip))


def test_no_phantom_counts_across_source_switch(mqtt_broker):
    dsn = load_config().database_url
    direct_ip = "192.168.7.3"
    mqtt_line = "10.5.5.5"
    config = make_config(plc_ip=direct_ip, lines={mqtt_line: ("127.0.0.1", mqtt_broker.port)})

    direct_reader = FakePlc()
    set_bit(direct_reader.outputs, 0, 6)  # P3 ON from the very start
    mqtt_reader = FakePlc()
    set_bit(mqtt_reader.outputs, 0, 6)  # P3 ON in the retained snapshot too
    publisher = LinePublisher(mqtt_reader, mqtt_line, "127.0.0.1", mqtt_broker.port, 50)

    def factory(cfg, name, line_ip=None):
        if name == "direct":
            return PlcPoller(direct_reader, dsn, 50, line_ip=direct_ip)
        return MqttLineSource("127.0.0.1", mqtt_broker.port, dsn, 50,
                              line_ip=line_ip, lines=cfg.lines, staleness_ms=1000)

    manager = SourceManager(config, initial_source="direct", factory=factory)
    try:
        cleanup_events(dsn, [direct_ip, mqtt_line])
        publisher.start()
        manager.start()

        # direct source: P3 ON at startup -> baseline only, no counts
        assert wait_for(lambda: manager.snapshot()["values"] is not None)
        time.sleep(0.3)
        assert cycles(dsn, direct_ip) == 0

        # switch to MQTT while P3 is ON there too: first snapshot is baseline
        manager.switch("mqtt", line_ip=mqtt_line)
        assert manager.source == "mqtt"
        assert wait_for(lambda: manager.snapshot()["values"] is not None)
        time.sleep(0.3)
        assert cycles(dsn, mqtt_line) == 0
        assert cycles(dsn, direct_ip) == 0

        # a genuine rising edge after the switch IS counted (new source is live)
        mqtt_reader.outputs = bytearray(2)  # P3 OFF first (falling edge: no event)
        assert wait_for(lambda: manager.snapshot()["values"]["lights"]["green"] is False)
        set_bit(mqtt_reader.outputs, 0, 6)  # P3 rising -> cycle_complete
        assert wait_for(lambda: cycles(dsn, mqtt_line) >= 1)
        assert cycles(dsn, direct_ip) == 0
    finally:
        manager.stop()
        publisher.stop()
        cleanup_events(dsn, [direct_ip, mqtt_line])


def test_direct_to_mqtt_and_back_end_to_end(mqtt_broker):
    dsn = load_config().database_url
    direct_ip = "192.168.7.3"
    mqtt_line = "10.6.6.6"
    config = make_config(plc_ip=direct_ip, lines={mqtt_line: ("127.0.0.1", mqtt_broker.port)})

    mqtt_reader = FakePlc()
    publisher = LinePublisher(mqtt_reader, mqtt_line, "127.0.0.1", mqtt_broker.port, 50)

    def factory(cfg, name, line_ip=None):
        if name == "direct":
            return PlcPoller(FakePlc(fail=True), dsn, 50, line_ip=direct_ip)  # unreachable PLC
        return MqttLineSource("127.0.0.1", mqtt_broker.port, dsn, 50,
                              line_ip=line_ip, lines=cfg.lines, staleness_ms=1000)

    manager = SourceManager(config, initial_source="direct", factory=factory)
    try:
        cleanup_events(dsn, [direct_ip, mqtt_line])
        publisher.start()
        manager.start()

        # direct with unreachable PLC: connecting -> stale, no events
        assert wait_for(lambda: manager.snapshot()["stale"])
        assert manager.snapshot()["values"] is None

        # switch to MQTT: retained snapshot arrives, edges count with mqtt line_ip
        manager.switch("mqtt", line_ip=mqtt_line)
        assert wait_for(lambda: manager.snapshot()["values"] is not None)
        set_bit(mqtt_reader.outputs, 0, 6)  # P3 rising -> cycle for the mqtt line
        assert wait_for(lambda: cycles(dsn, mqtt_line) >= 1)

        # switch back to direct (still unreachable): cleared, then stale, no events
        manager.switch("direct")
        snap = manager.snapshot()
        assert snap["source"] == "direct" and snap["values"] is None
        assert wait_for(lambda: manager.snapshot()["stale"])
        time.sleep(0.3)
        assert cycles(dsn, direct_ip) == 0
        assert cycles(dsn, mqtt_line) >= 1  # mqtt events untouched
    finally:
        manager.stop()
        publisher.stop()
        cleanup_events(dsn, [direct_ip, mqtt_line])
