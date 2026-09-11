"""End-to-end MQTT integration test: broker + publisher + dashboard source.

Runs in the default test suite: no PLC needed (fake reader), no external
broker (in-process amqtt), no database (events are captured in memory).
"""

import time

from app.mqtt_source import MqttLineSource
from app.publisher import LinePublisher


class FakeReader:
    def __init__(self):
        self.inputs = bytearray(2)
        self.outputs = bytearray(2)
        self.fail = False

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


def test_mqtt_round_trip_and_silence_liveness(mqtt_broker):
    reader = FakeReader()
    publisher = LinePublisher(reader, "127.0.0.1", mqtt_broker.port, poll_interval_ms=50)
    recorded: list[str] = []
    source = MqttLineSource(
        broker_host="127.0.0.1",
        broker_port=mqtt_broker.port,
        staleness_ms=1000,
        on_event=recorded.append,
    )
    try:
        publisher.start()
        source.start()

        # 1) fresh packets arrive; the first is baseline, values render
        assert wait_for(lambda: source.snapshot()["values"] is not None), (
            "dashboard never received a plc_tags snapshot"
        )
        assert source.snapshot()["stale"] is False
        assert source.snapshot()["source"] == "mqtt"
        assert source.snapshot()["broker"] == f"127.0.0.1:{mqtt_broker.port}"

        # 2) edge counting after baseline: P3 rising -> cycle_complete recorded
        set_bit(reader.outputs, 0, 6)
        assert wait_for(lambda: "cycle_complete" in recorded), (
            "P3 rising edge was not counted"
        )

        # no duplicates while P3 stays ON
        time.sleep(0.3)
        assert recorded.count("cycle_complete") == 1

        # 3) publisher crash: packets stop, silence (~1 s) marks stale,
        #    values stay frozen (no LWT, no status topic involved)
        frozen_update = source.snapshot()["last_update"]
        frozen_green = source.snapshot()["values"]["lights"]["green"]
        sock = publisher._mqtt.socket()
        assert sock is not None
        sock.close()
        publisher._stop.set()
        assert wait_for(lambda: source.snapshot()["stale"], timeout=10), (
            "silence did not mark the connection stale"
        )
        snap = source.snapshot()
        assert snap["values"]["lights"]["green"] is frozen_green  # frozen, not blanked
        assert snap["last_update"] == frozen_update
    finally:
        source.stop()
        publisher.stop()
