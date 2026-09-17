"""Broker authentication and topic-lock tests (live in-process amqtt)."""

"""Broker authentication and topic-lock tests (live in-process amqtt)."""

import asyncio
import time

import paho.mqtt.client as mqtt

from app.broker import create_broker
from app.mqtt_proto import TAGS_TOPIC
from tests.conftest import TEST_MQTT_PASSWORD, TEST_MQTT_USERNAME


def test_broker_config_requires_credentials_and_locks_topic():
    # Broker() requires a running event loop: build it inside asyncio.run
    broker = asyncio.run(_build_broker())
    plugins = broker.config.plugins
    assert plugins["amqtt.plugins.authentication.AnonymousAuthPlugin"] == {
        "allow_anonymous": False
    }
    assert plugins["amqtt.plugins.authentication.FileAuthPlugin"]["password_file"]
    assert plugins["amqtt.plugins.topic_checking.TopicAccessControlListPlugin"] == {
        "publish_acl": {TEST_MQTT_USERNAME: ["plc_tags"]},
        "acl": {TEST_MQTT_USERNAME: ["plc_tags"]},
    }


async def _build_broker():
    return create_broker(12345, TEST_MQTT_USERNAME, TEST_MQTT_PASSWORD)


class Probe:
    """Minimal paho probe capturing CONNACK, SUBACK, and messages."""

    def __init__(self, port: int, username: str | None = None, password: str | None = None):
        self.connected: bool | None = None
        self.granted = None
        self.messages: list[tuple[str, bytes]] = []
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if username is not None:
            self.client.username_pw_set(username, password or "")
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message
        self.client.connect("127.0.0.1", port)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = not reason_code.is_failure

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties=None):
        self.granted = list(reason_codes)

    def _on_message(self, client, userdata, msg):
        self.messages.append((msg.topic, msg.payload))

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()


def wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_anonymous_client_refused(mqtt_broker):
    probe = Probe(mqtt_broker.port)  # no credentials
    try:
        assert wait_for(lambda: probe.connected is False)
    finally:
        probe.stop()


def test_wrong_password_refused(mqtt_broker):
    probe = Probe(mqtt_broker.port, TEST_MQTT_USERNAME, "wrong")
    try:
        assert wait_for(lambda: probe.connected is False)
    finally:
        probe.stop()


def test_authorized_client_connects_and_receives(mqtt_broker):
    probe = Probe(mqtt_broker.port, TEST_MQTT_USERNAME, TEST_MQTT_PASSWORD)
    try:
        assert wait_for(lambda: probe.connected is True)
        probe.client.subscribe([(TAGS_TOPIC, 0)])
        assert wait_for(lambda: probe.granted is not None)
        assert all(code.value == 0 for code in probe.granted)
    finally:
        probe.stop()


def test_authorized_client_cannot_subscribe_other_topics(mqtt_broker):
    probe = Probe(mqtt_broker.port, TEST_MQTT_USERNAME, TEST_MQTT_PASSWORD)
    try:
        assert wait_for(lambda: probe.connected is True)
        probe.granted = None
        probe.client.subscribe([(TAGS_TOPIC, 0), ("intruder/topic", 0)])
        assert wait_for(lambda: probe.granted is not None)
        values = [code.value for code in probe.granted]
        assert values[0] == 0  # plc_tags granted
        assert values[1] == 0x80  # intruder/topic refused
    finally:
        probe.stop()


def test_unauthorized_publish_is_not_relayed(mqtt_broker):
    publisher = Probe(mqtt_broker.port, TEST_MQTT_USERNAME, TEST_MQTT_PASSWORD)
    subscriber = Probe(mqtt_broker.port, TEST_MQTT_USERNAME, TEST_MQTT_PASSWORD)
    try:
        assert wait_for(lambda: publisher.connected is True and subscriber.connected is True)
        subscriber.client.subscribe([(TAGS_TOPIC, 0)])
        assert wait_for(lambda: subscriber.granted is not None)
        publisher.client.publish(TAGS_TOPIC, b'{"ESO": false}')
        assert wait_for(lambda: subscriber.messages)
        # a second topic with a valid payload shape never gets through:
        # the publish ACL drops it before distribution
        before = len(subscriber.messages)
        publisher.client.publish("intruder/topic", b'{"ESO": false}')
        time.sleep(0.4)
        assert len(subscriber.messages) == before
    finally:
        publisher.stop()
        subscriber.stop()
