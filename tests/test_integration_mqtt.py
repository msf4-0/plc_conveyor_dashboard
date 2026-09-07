"""End-to-end MQTT integration test: broker + publisher + dashboard source.

Runs in the default test suite: no PLC needed (fake reader), no external
broker (in-process amqtt). Requires the local PostgreSQL server.
"""

import time

import paho.mqtt.client as mqtt

from app.config import load_config
from app.db import connect_db, per_minute_counts
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


def cleanup_events(dsn, event_type):
    with connect_db(dsn) as conn:
        conn.execute("DELETE FROM line_events WHERE event_type = %s", (event_type,))
        conn.commit()


def test_mqtt_round_trip_edges_and_lwt(mqtt_broker):
    dsn = load_config().database_url
    line_ip = "10.7.7.7"
    reader = FakeReader()
    publisher = LinePublisher(reader, line_ip, "127.0.0.1", mqtt_broker.port, poll_interval_ms=50)
    source = MqttLineSource(
        broker_host="127.0.0.1",
        broker_port=mqtt_broker.port,
        dsn=dsn,
        poll_interval_ms=50,
        line_ip=line_ip,
        staleness_ms=1000,
    )
    try:
        publisher.start()
        source.start()

        # 1) retained snapshot delivered immediately on subscribe
        assert wait_for(lambda: source.snapshot()["values"] is not None), (
            "dashboard never received a retained snapshot"
        )
        assert source.snapshot()["stale"] is False
        assert source.snapshot()["source"] == "mqtt"

        # 2) edge counting after baseline: P3 rising -> cycle_complete persisted
        set_bit(reader.outputs, 0, 6)
        assert wait_for(lambda: any(
            p["cycles"] for p in per_minute_counts(dsn, line_ip=line_ip)
        )), "P3 rising edge was not counted"

        # no duplicates while P3 stays ON
        time.sleep(0.3)
        counts = [p["cycles"] for p in per_minute_counts(dsn, line_ip=line_ip)]
        assert sum(counts) == 1

        # 3) publisher crash: LWT offline -> dashboard goes stale, values frozen
        frozen_update = source.snapshot()["last_update"]
        sock = publisher._mqtt.socket()
        assert sock is not None
        sock.close()
        assert wait_for(lambda: source.snapshot()["stale"]), "LWT offline did not mark stale"
        snap = source.snapshot()
        assert snap["values"]["lights"]["green"] is True  # frozen, not blanked
        assert snap["last_update"] == frozen_update
    finally:
        source.stop()
        publisher.stop()
        cleanup_events(dsn, "cycle_complete")
        cleanup_events(dsn, "metal_detected")
