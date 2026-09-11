import time

import paho.mqtt.client as mqtt
import pytest

from app.mqtt_proto import TAGS_TOPIC, parse_payload
from app.publisher import LinePublisher
from app.tags import raw_values


class FakeReader:
    """Fake PLC: fixed 2-byte I/Q dumps, counts reads, can fail."""

    def __init__(self):
        self.inputs = bytearray(2)
        self.outputs = bytearray(2)
        self.read_count = 0
        self.fail = False

    def connect(self):
        if self.fail:
            raise ConnectionError("no route to PLC")

    def read(self):
        self.read_count += 1
        if self.fail:
            raise ConnectionError("comms lost")
        return bytes(self.inputs), bytes(self.outputs)

    def close(self):
        pass


class Collector:
    def __init__(self, port: int):
        self.messages: list[tuple[str, bytes, bool]] = []
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_message = self._on_message
        self.client.connect("127.0.0.1", port)
        self.client.loop_start()
        self.client.subscribe([(TAGS_TOPIC, 0)])

    def _on_message(self, client, userdata, msg):
        self.messages.append((msg.topic, msg.payload, msg.retain))

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def tags(self):
        return [m for m in self.messages if m[0] == TAGS_TOPIC]

    def wait_for(self, predicate, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate(self.messages):
                return True
            time.sleep(0.05)
        return False


@pytest.fixture()
def publisher(mqtt_broker):
    reader = FakeReader()
    pub = LinePublisher(reader, "127.0.0.1", mqtt_broker.port, poll_interval_ms=50)
    yield reader, pub
    if pub._thread is not None:
        pub.stop()


def test_publisher_cadence_payload_and_no_retain(publisher, mqtt_broker):
    reader, pub = publisher
    collector = Collector(mqtt_broker.port)
    try:
        pub.start()
        assert collector.wait_for(
            lambda ms: sum(1 for m in ms if m[0] == TAGS_TOPIC) >= 3, timeout=5
        )
        # payload carries exactly the tag booleans the publisher read
        payload = parse_payload(collector.tags()[-1][1])
        expected = raw_values(bytes(reader.inputs), bytes(reader.outputs))
        assert payload == expected
        # no retain flag: a late subscriber must wait for a fresh packet
        assert all(not m[2] for m in collector.messages)
        # nothing is ever published to a status topic
        assert all(m[0] == TAGS_TOPIC for m in collector.messages)
        # PLC failure: no new snapshots while it lasts
        reader.fail = True
        count_at_fail = len(collector.tags())
        time.sleep(0.3)
        assert len(collector.tags()) == count_at_fail
        reader.fail = False
    finally:
        collector.stop()


def test_publisher_clean_stop_publishes_nothing_extra(publisher, mqtt_broker):
    reader, pub = publisher
    collector = Collector(mqtt_broker.port)
    try:
        pub.start()
        assert collector.wait_for(lambda ms: any(m[0] == TAGS_TOPIC for m in ms))
    finally:
        collector.stop()
    pub.stop()
    collector = Collector(mqtt_broker.port)
    try:
        # no retained snapshot, no status message: a new subscriber gets nothing
        time.sleep(0.5)
        assert collector.messages == []
    finally:
        collector.stop()
