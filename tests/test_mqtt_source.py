import json
import time

import pytest
from paho.mqtt.reasoncodes import ReasonCode

from app.mqtt_proto import TAGS_TOPIC, encode_payload
from app.mqtt_source import DEFAULT_STALENESS_MS, MqttLineSource
from app.tags import TAGS

LABELS = list(TAGS)


def raw(**overrides):
    values = {label: False for label in LABELS}
    values.update(overrides)
    return values


class FakePahoClient:
    """Captures subscriptions; delivers scripted messages to on_message."""

    def __init__(self):
        self.subscriptions: list = []
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

    # test helpers
    def fire_connect(self, ok=True):
        # CONNACK reason code; "Not authorized" is a v5 failure code (0x87)
        self.on_connect(self, None, {}, ReasonCode(2, "Success" if ok else "Not authorized"), None)

    def fire_tags(self, values: dict):
        self.on_message(self, None, type("M", (), {
            "topic": TAGS_TOPIC,
            "payload": encode_payload(values),
        })())

    def fire_raw(self, payload: bytes, topic: str = TAGS_TOPIC):
        self.on_message(self, None, type("M", (), {
            "topic": topic,
            "payload": payload,
        })())


def make_source(client, staleness_ms=DEFAULT_STALENESS_MS, on_event=None):
    return MqttLineSource(
        broker_host="192.168.0.11",
        broker_port=1883,
        staleness_ms=staleness_ms,
        on_event=on_event,
        client_factory=lambda: client,
    )


@pytest.fixture()
def source():
    client = FakePahoClient()
    recorded: list[str] = []
    src = make_source(client, on_event=recorded.append)
    src.start()
    client.fire_connect()
    return client, src, recorded


def test_connect_subscribes_only_to_plc_tags(source):
    client, src, _ = source
    assert client.subscriptions == [[(TAGS_TOPIC, 0)]]
    assert src.broker == "192.168.0.11:1883"


def test_first_snapshot_is_baseline_and_shows_values(source):
    client, src, recorded = source
    client.fire_tags(raw(P3=True))  # P3 ON at first sight: must not count
    assert recorded == []  # baseline, no phantom event
    snap = src.snapshot()
    assert snap["values"]["lights"]["green"] is True
    assert snap["stale"] is False and snap["connected"] is True
    assert snap["source"] == "mqtt" and snap["broker"] == "192.168.0.11:1883"
    assert "line_ip" not in snap and "lines" not in snap


def test_edge_counted_after_baseline(source):
    client, src, recorded = source
    client.fire_tags(raw())  # baseline, P3 off
    client.fire_tags(raw(P3=True))  # P3 rising -> cycle
    assert "cycle_complete" in recorded
    client.fire_tags(raw(P3=True))  # stays ON: no duplicate
    assert recorded.count("cycle_complete") == 1


def test_stale_after_silence_and_rebaseline_on_resume(source):
    client, src, recorded = source
    client.fire_tags(raw(P3=True))  # baseline snapshot, P3 already ON
    time.sleep(1.1)  # > DEFAULT_STALENESS_MS (1000)
    assert src.snapshot()["stale"] is True
    # P3 already ON when data resumes: re-baseline, no phantom count
    client.fire_tags(raw(P3=True))
    snap = src.snapshot()
    assert snap["stale"] is False
    assert recorded == []
    # counting resumes only on a later rising edge across the re-baseline
    client.fire_tags(raw())  # P3 falling: no event
    client.fire_tags(raw(P3=True))  # P3 rising: counted
    assert recorded == ["cycle_complete"]


def test_values_frozen_while_stale(source):
    client, src, _ = source
    client.fire_tags(raw(P3=True))
    frozen = src.snapshot()
    time.sleep(1.1)
    snap = src.snapshot()
    assert snap["stale"] is True
    assert snap["values"]["lights"]["green"] is True  # frozen, not blanked
    assert snap["last_update"] == frozen["last_update"]


def test_message_on_other_topic_ignored(source):
    client, src, recorded = source
    client.fire_raw(b'{"ESO": true}', topic="some/other/topic")
    client.fire_tags(raw())
    assert src.snapshot()["values"] is not None
    assert recorded == []


def test_malformed_payload_discarded(source):
    client, src, recorded = source
    client.fire_raw(b"{bad json")
    assert src.snapshot()["values"] is None
    assert recorded == []


def test_strict_payload_with_missing_label_discarded(source):
    client, src, recorded = source
    client.fire_raw(json.dumps({k: False for k in LABELS if k != "B4"}))
    assert src.snapshot()["values"] is None
    assert recorded == []
