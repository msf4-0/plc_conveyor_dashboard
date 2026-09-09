import time

import pytest

from app.config import Config
from app.source_manager import SourceManager


class FakeSource:
    def __init__(self, name, line_ip=None, broker=None):
        self.name = name
        self.started = False
        self.stopped = False
        self._snapshot = {
            "connected": True, "stale": False, "connecting": False,
            "server_time": "t", "last_update": "t", "values": None,
            "line_ip": line_ip, "broker": broker, "source": name,
        }
        self.fail_start = False

    def start(self):
        if self.fail_start:
            raise RuntimeError("start failed")
        self.started = True

    def stop(self):
        self.stopped = True

    def snapshot(self):
        return self._snapshot

    @property
    def line_ip(self):
        return self._snapshot["line_ip"]

    @property
    def broker(self):
        return self._snapshot["broker"]


def make_config(**overrides):
    kwargs = dict(
        plc_ip="192.168.5.3", plc_rack=0, plc_slot=1, poll_interval_ms=500,
        host="h", port=1, data_source="direct",
    )
    kwargs.update(overrides)
    return Config(**kwargs)


class FakeFactory:
    """Records build calls; hands out scripted fake sources."""

    def __init__(self, sources=None):
        self.calls = []
        self.sources = list(sources or [])

    def __call__(self, config, name, broker=None, on_event=None):
        self.calls.append((name, broker))
        if self.sources:
            src = self.sources.pop(0)
            src.name = name
            if name == "direct":
                src._snapshot["line_ip"] = config.plc_ip
            if name == "mqtt" and broker is not None:
                src._snapshot["broker"] = f"{broker[0]}:{broker[1]}"
            return src
        if name == "mqtt" and broker is None:
            from app.source_manager import InactiveMqttSource

            return InactiveMqttSource()
        return FakeSource(name, line_ip=config.plc_ip if name == "direct" else None,
                          broker=f"{broker[0]}:{broker[1]}" if name == "mqtt" else None)


def make_manager(factory, initial="direct", **kwargs):
    return SourceManager(make_config(), initial_source=initial, factory=factory, **kwargs)


def test_delegation_and_properties():
    factory = FakeFactory()
    mgr = make_manager(factory, initial="direct")
    mgr.start()
    mgr.stop()
    assert mgr.snapshot()["source"] == "direct"
    assert mgr.source == "direct"
    assert mgr.line_ip == "192.168.5.3"
    assert mgr.connection == "192.168.5.3"


def test_unknown_initial_source_rejected():
    with pytest.raises(ValueError):
        make_manager(FakeFactory(), initial="modbus")


def test_build_source_unknown_name_raises():
    from app.source_manager import build_source

    with pytest.raises(ValueError):
        build_source(make_config(), "modbus")


def test_build_source_mqtt_with_broker():
    from app.source_manager import build_source

    src = build_source(make_config(), "mqtt", broker=("192.168.0.11", 1883))
    assert src._broker == ("192.168.0.11", 1883)
    assert src.broker == "192.168.0.11:1883"


def test_build_source_mqtt_without_broker_is_inactive_slot():
    from app.source_manager import build_source

    src = build_source(make_config(), "mqtt")
    snap = src.snapshot()
    assert snap["connecting"] is True and snap["stale"] is False
    assert snap["broker"] is None and snap["values"] is None
    src.start()  # no-op
    src.stop()


def test_startup_mqtt_without_broker_stays_inactive():
    factory = FakeFactory()
    mgr = make_manager(factory, initial="mqtt")
    mgr.start()
    snap = mgr.snapshot()
    assert mgr.source == "mqtt"
    assert snap["connecting"] is True and snap["broker"] is None
    assert mgr.broker is None and mgr.connection is None


def test_switch_swaps_sources_and_stops_old():
    old, new = FakeSource("direct"), FakeSource("mqtt")
    factory = FakeFactory(sources=[old, new])
    mgr = make_manager(factory, initial="direct")
    mgr.switch("mqtt", broker=("192.168.0.11", 1883))
    assert old.stopped is True and new.started is True
    assert mgr.source == "mqtt"
    assert mgr.connection == "192.168.0.11:1883"
    assert factory.calls == [
        ("direct", None),
        ("mqtt", ("192.168.0.11", 1883)),
    ]


def test_switch_to_same_source_is_noop():
    old = FakeSource("direct")
    factory = FakeFactory(sources=[old])
    mgr = make_manager(factory, initial="direct")
    snap = mgr.switch("direct")
    assert old.stopped is False
    assert snap is old._snapshot
    assert len(factory.calls) == 1  # no new build


def test_switch_to_same_broker_is_noop():
    old = FakeSource("mqtt", broker="192.168.0.11:1883")
    factory = FakeFactory(sources=[FakeSource("direct"), old])
    mgr = make_manager(factory, initial="direct")
    mgr.switch("mqtt", broker=("192.168.0.11", 1883))
    snap = mgr.switch("mqtt", broker=("192.168.0.11", 1883))
    assert old.stopped is False
    assert snap is old._snapshot
    assert len(factory.calls) == 2  # only the initial build + the switch build


def test_retype_new_broker_rebuilds_mqtt_source():
    old = FakeSource("mqtt", broker="192.168.0.11:1883")
    new = FakeSource("mqtt", broker="192.168.0.12:1884")
    factory = FakeFactory(sources=[FakeSource("direct"), old, new])
    mgr = make_manager(factory, initial="direct")
    mgr.switch("mqtt", broker=("192.168.0.11", 1883))
    mgr.switch("mqtt", broker=("192.168.0.12", 1884))
    assert old.stopped is True and new.started is True
    assert mgr.connection == "192.168.0.12:1884"
    assert factory.calls[-1] == ("mqtt", ("192.168.0.12", 1884))


def test_switch_to_mqtt_without_broker_rejected():
    old = FakeSource("direct")
    factory = FakeFactory(sources=[old])
    mgr = make_manager(factory, initial="direct")
    with pytest.raises(ValueError):
        mgr.switch("mqtt")
    assert old.stopped is False
    assert mgr.source == "direct"


def test_switch_build_failure_keeps_old():
    class ExplodingFactory:
        def __init__(self, old):
            self.old = old

        def __call__(self, config, name, broker=None, on_event=None):
            if name == "mqtt":
                raise RuntimeError("bad broker config")
            return self.old

    old = FakeSource("direct")
    mgr = SourceManager(make_config(), initial_source="direct", factory=ExplodingFactory(old))
    with pytest.raises(RuntimeError):
        mgr.switch("mqtt", broker=("192.168.0.11", 1883))
    assert mgr.source == "direct"
    assert old.stopped is False


def test_switch_start_failure_keeps_old():
    new = FakeSource("mqtt")
    new.fail_start = True
    old = FakeSource("direct")
    factory = FakeFactory(sources=[old, new])
    mgr = make_manager(factory, initial="direct")
    with pytest.raises(RuntimeError):
        mgr.switch("mqtt", broker=("192.168.0.11", 1883))
    assert mgr.source == "direct"
    assert old.stopped is False


# ---------------------------------------------------------------------------
# Count integrity across source switches (real sources, fake PLC readers)
# ---------------------------------------------------------------------------

from app.mqtt_source import MqttLineSource
from app.plc import PlcPoller
from app.publisher import LinePublisher
from app.stats import MinuteCounter


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


def test_no_phantom_counts_across_source_switch(mqtt_broker):
    direct_ip = "192.168.7.3"
    broker = ("127.0.0.1", mqtt_broker.port)
    config = make_config(plc_ip=direct_ip)

    direct_reader = FakePlc()
    set_bit(direct_reader.outputs, 0, 6)  # P3 ON from the very start
    mqtt_reader = FakePlc()
    set_bit(mqtt_reader.outputs, 0, 6)  # P3 ON from the very start
    publisher = LinePublisher(mqtt_reader, "127.0.0.1", mqtt_broker.port, 50)

    recorded: list[str] = []

    def factory(cfg, name, broker=None, on_event=None):
        if name == "direct":
            return PlcPoller(direct_reader, 50, line_ip=direct_ip, on_event=on_event)
        return MqttLineSource(broker[0], broker[1], 50, staleness_ms=1000,
                              on_event=on_event)

    manager = SourceManager(config, initial_source="direct", on_event=recorded.append,
                            factory=factory)
    try:
        publisher.start()
        manager.start()

        # direct source: P3 ON at startup -> baseline only, no counts
        assert wait_for(lambda: manager.snapshot()["values"] is not None)
        time.sleep(0.3)
        assert recorded == []

        # switch to MQTT while P3 is ON there too: first snapshot is baseline
        manager.switch("mqtt", broker=broker)
        assert manager.source == "mqtt"
        assert wait_for(lambda: manager.snapshot()["values"] is not None)
        time.sleep(0.3)
        assert recorded == []

        # a genuine rising edge after the switch IS counted (new source is live)
        mqtt_reader.outputs = bytearray(2)  # P3 OFF first (falling edge: no event)
        assert wait_for(lambda: manager.snapshot()["values"]["lights"]["green"] is False)
        set_bit(mqtt_reader.outputs, 0, 6)  # P3 rising -> cycle_complete
        assert wait_for(lambda: recorded.count("cycle_complete") >= 1)
    finally:
        manager.stop()
        publisher.stop()


def test_direct_to_mqtt_and_back_end_to_end(mqtt_broker):
    direct_ip = "192.168.7.3"
    broker = ("127.0.0.1", mqtt_broker.port)
    config = make_config(plc_ip=direct_ip)

    mqtt_reader = FakePlc()
    publisher = LinePublisher(mqtt_reader, "127.0.0.1", mqtt_broker.port, 50)

    def factory(cfg, name, broker=None, on_event=None):
        if name == "direct":
            return PlcPoller(FakePlc(fail=True), 50, line_ip=direct_ip, on_event=on_event)  # unreachable PLC
        return MqttLineSource(broker[0], broker[1], 50, staleness_ms=1000,
                              on_event=on_event)

    recorded: list[str] = []
    manager = SourceManager(config, initial_source="direct", on_event=recorded.append,
                            factory=factory)
    try:
        publisher.start()
        manager.start()

        # direct with unreachable PLC: connecting -> stale, no events
        assert wait_for(lambda: manager.snapshot()["stale"])
        assert manager.snapshot()["values"] is None

        # switch to MQTT: fresh packets arrive, P3 rising edge is counted
        manager.switch("mqtt", broker=broker)
        assert wait_for(lambda: manager.snapshot()["values"] is not None)
        set_bit(mqtt_reader.outputs, 0, 6)  # P3 rising -> cycle_complete
        assert wait_for(lambda: recorded.count("cycle_complete") >= 1)

        # switch back to direct (still unreachable): cleared, then stale, no events
        before = recorded.count("cycle_complete")
        manager.switch("direct")
        snap = manager.snapshot()
        assert snap["source"] == "direct" and snap["values"] is None
        assert wait_for(lambda: manager.snapshot()["stale"])
        time.sleep(0.3)
        assert recorded.count("cycle_complete") == before  # no further events
    finally:
        manager.stop()
        publisher.stop()


# ---------------------------------------------------------------------------
# Counter reset hooks: switch/broker change resets, same target does not
# ---------------------------------------------------------------------------


def test_switch_fires_on_connection_change():
    resets = []
    factory = FakeFactory(sources=[FakeSource("direct"), FakeSource("mqtt")])
    mgr = make_manager(factory, initial="direct",
                       on_connection_change=lambda: resets.append(1))
    mgr.switch("mqtt", broker=("192.168.0.11", 1883))
    assert len(resets) == 1


def test_switch_start_failure_does_not_fire_connection_change():
    resets = []
    new = FakeSource("mqtt")
    new.fail_start = True
    factory = FakeFactory(sources=[FakeSource("direct"), new])
    mgr = make_manager(factory, initial="direct", on_connection_change=resets.append)
    with pytest.raises(RuntimeError):
        mgr.switch("mqtt", broker=("192.168.0.11", 1883))
    assert resets == []


def test_broker_change_fires_reset_and_same_broker_does_not():
    resets = []
    factory = FakeFactory(sources=[FakeSource("direct"), FakeSource("mqtt"),
                                   FakeSource("mqtt")])
    mgr = make_manager(factory, initial="direct",
                       on_connection_change=lambda: resets.append(1))
    mgr.switch("mqtt", broker=("192.168.0.11", 1883))
    assert len(resets) == 1  # source switch fired
    mgr.switch("mqtt", broker=("192.168.0.12", 1883))
    assert len(resets) == 2  # genuine broker change fires again
    mgr.switch("mqtt", broker=("192.168.0.12", 1883))
    assert len(resets) == 2  # same-broker resubmit: no reset


def test_counter_reset_wired_through_switch():
    counter = MinuteCounter()
    counter.record("cycle_complete")
    factory = FakeFactory(sources=[FakeSource("direct"), FakeSource("mqtt")])
    mgr = make_manager(factory, initial="direct", on_connection_change=counter.reset)
    assert counter.snapshot(window_minutes=1)[0]["cycles"] == 1
    mgr.switch("mqtt", broker=("192.168.0.11", 1883))
    assert counter.snapshot(window_minutes=1)[0]["cycles"] == 0
