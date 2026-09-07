import time

import pytest

from app.mqtt_proto import encode_snapshot, state_topic, status_topic
from app.mqtt_source import MqttLineSource


class FakePahoClient:
    """Captures subscriptions; delivers scripted messages to on_message."""

    def __init__(self):
        self.subscriptions: list = []
        self.unsubscriptions: list = []
        self.on_connect = None
        self.on_message = None
        self.on_disconnect = None

    def connect_async(self, host, port, keepalive=30):
        pass

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def subscribe(self, topics, *args, **kwargs):
        self.subscriptions.append(topics)

    def unsubscribe(self, topics, *args, **kwargs):
        self.unsubscriptions.append(topics)

    # test helpers
    def fire_connect(self, ok=True):
        self.on_connect(self, None, {}, 0 if ok else 5, None)

    def fire_state(self, line_ip, inputs, outputs):
        self.on_message(self, None, type("M", (), {
            "topic": state_topic(line_ip),
            "payload": encode_snapshot(line_ip, inputs, outputs),
        })())

    def fire_status(self, line_ip, status: bytes):
        self.on_message(self, None, type("M", (), {
            "topic": status_topic(line_ip),
            "payload": status,
        })())


def set_bit(data: bytearray, byte: int, bit: int):
    data[byte] |= 1 << bit


def make_source(client, lines=None, staleness_ms=500):
    return MqttLineSource(
        broker_host="127.0.0.1",
        broker_port=1883,
        dsn="unused://dsn",  # persistence is patched per-test
        poll_interval_ms=500,
        line_ip="10.0.0.1",
        lines=lines,
        staleness_ms=staleness_ms,
        client_factory=lambda: client,
    )


@pytest.fixture()
def source(monkeypatch):
    client = FakePahoClient()
    persisted = []
    monkeypatch.setattr(
        "app.mqtt_source.insert_event",
        lambda dsn, event_type, line_ip="": persisted.append((line_ip, event_type)) or len(persisted),
    )
    src = make_source(client)
    persisted_collector = persisted
    src.start()
    client.fire_connect()
    return client, src, persisted_collector


def test_connect_subscribes_to_line_topics(source):
    client, src, _ = source
    topics = [t for t in client.subscriptions[0]]
    assert (state_topic("10.0.0.1"), 0) in topics
    assert (status_topic("10.0.0.1"), 0) in topics


def test_first_snapshot_is_baseline_and_shows_values(source):
    client, src, persisted = source
    outputs = bytearray(2)
    set_bit(outputs, 0, 6)  # P3 ON at first sight: must not count
    client.fire_state("10.0.0.1", bytearray(2), outputs)
    assert persisted == []  # baseline, no phantom event
    snap = src.snapshot()
    assert snap["values"]["lights"]["green"] is True
    assert snap["stale"] is False and snap["connected"] is True
    assert snap["source"] == "mqtt" and snap["line_ip"] == "10.0.0.1"


def test_edge_counted_after_baseline(source):
    client, src, persisted = source
    client.fire_state("10.0.0.1", bytearray(2), bytearray(2))  # baseline, P3 off
    outputs = bytearray(2)
    set_bit(outputs, 0, 6)
    client.fire_state("10.0.0.1", bytearray(2), outputs)  # P3 rising -> cycle
    assert ("10.0.0.1", "cycle_complete") in persisted
    outputs2 = bytearray(outputs)
    client.fire_state("10.0.0.1", bytearray(2), outputs2)  # stays ON: no duplicate
    assert persisted.count(("10.0.0.1", "cycle_complete")) == 1


def test_stale_after_silence_and_rebaseline_on_resume(source):
    client, src, persisted = source
    client.fire_state("10.0.0.1", bytearray(2), bytearray(2))
    time.sleep(0.6)  # > staleness_ms (500)
    assert src.snapshot()["stale"] is True
    # P3 already ON when data resumes: baseline, no phantom count
    outputs = bytearray(2)
    set_bit(outputs, 0, 6)
    client.fire_state("10.0.0.1", bytearray(2), outputs)
    snap = src.snapshot()
    assert snap["stale"] is False
    assert persisted == []


def test_lwt_offline_marks_stale_values_frozen(source):
    client, src, _ = source
    outputs = bytearray(2)
    set_bit(outputs, 0, 6)
    client.fire_state("10.0.0.1", bytearray(2), outputs)
    before = src.snapshot()["last_update"]
    client.fire_status("10.0.0.1", b"offline")
    snap = src.snapshot()
    assert snap["stale"] is True
    assert snap["values"]["lights"]["green"] is True  # frozen, not blanked
    assert snap["last_update"] == before
    client.fire_status("10.0.0.1", b"online")
    assert src.snapshot()["stale"] is False


def test_set_line_clears_state_rebaselines_and_switches_topics(source):
    client, src, persisted = source
    lines = {"10.0.0.1": ("127.0.0.1", 1883), "10.0.0.2": ("127.0.0.1", 1883)}
    src2_lines = lines
    client2 = FakePahoClient()
    # reuse same source with registry: rebuild through set_line path is validated
    # via a source created with lines
    client.fire_state("10.0.0.1", bytearray(2), bytearray(2))
    src.set_line("10.0.0.1")  # switch to a line not in registry must raise only when registry set
    # build registry-aware source to test validation + topic switch
    src_lines = MqttLineSource(
        broker_host="h", broker_port=1, dsn="u", poll_interval_ms=500,
        line_ip="10.0.0.1", lines=src2_lines, client_factory=lambda: client,
    )
    with pytest.raises(ValueError):
        src_lines.set_line("10.9.9.9")
    src_lines.set_line("10.0.0.2")
    assert src_lines.snapshot()["line_ip"] == "10.0.0.2"
    assert src_lines.snapshot()["values"] is None  # cleared -> connecting
    # messages from the old line are ignored
    outputs = bytearray(2)
    set_bit(outputs, 0, 6)
    client.fire_state("10.0.0.1", bytearray(2), outputs)
    assert src_lines.snapshot()["values"] is None
    assert persisted == []
    client.fire_state("10.0.0.2", bytearray(2), bytearray(2))  # baseline for new line
    assert src_lines.snapshot()["values"]["lights"]["green"] is False


def test_malformed_snapshot_discarded(source):
    client, src, persisted = source
    client.on_message(client, None, type("M", (), {
        "topic": state_topic("10.0.0.1"), "payload": b"{bad json",
    })())
    assert src.snapshot()["values"] is None
    assert persisted == []
