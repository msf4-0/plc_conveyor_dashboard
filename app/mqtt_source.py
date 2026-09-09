import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from app.edges import detect_events
from app.mqtt_proto import TAGS_TOPIC, parse_payload
from app.plc import build_view

log = logging.getLogger(__name__)

DEFAULT_STALENESS_MS = 1000  # ~2 poll intervals at 500 ms; 1 s silence = stale


def make_paho_client() -> mqtt.Client:
    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


class MqttLineSource:
    """Dashboard-side subscriber for one MQTT broker at a time.

    Subscribes to the single fixed topic `plc_tags`, decodes the strict
    label->boolean payload, detects P3/B4 rising edges (baseline-only on
    connect/switch/stale resume) and hands events to the dashboard-owned
    counter. Liveness is packet cadence alone: stale while no packet has
    arrived for `staleness_ms` (there is no status topic).
    """

    def __init__(
        self,
        broker_host: str,
        broker_port: int,
        poll_interval_ms: int,
        staleness_ms: int = DEFAULT_STALENESS_MS,
        on_event: Callable[[str], None] | None = None,
        client_factory=make_paho_client,
    ):
        self._broker = (broker_host, broker_port)
        self._on_event = on_event
        self._staleness_ms = staleness_ms
        self._lock = threading.Lock()
        self._broker_connected = False
        self._raw: dict[str, bool] | None = None
        self._previous_raw: dict[str, bool] | None = None
        self._baseline = True  # first snapshot after connect/switch/stale: no events
        self._last_recv: float | None = None
        self._timestamp: str | None = None
        self._client = client_factory()
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self._client.connect_async(*self._broker, keepalive=30)
        self._client.loop_start()

    def stop(self) -> None:
        try:
            self._client.disconnect()
            self._client.loop_stop()
        except Exception:
            log.exception("Error while disconnecting MQTT source")

    # -- paho callbacks ------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        is_failure = getattr(reason_code, "is_failure", None)
        failed = is_failure() if callable(is_failure) else (
            is_failure if isinstance(is_failure, bool) else reason_code != 0
        )
        if failed:
            log.warning("Broker connection refused: %s", reason_code)
            return
        log.info("Connected to broker %s:%s", *self._broker)
        self._broker_connected = True
        client.subscribe([(TAGS_TOPIC, 0)])

    def _on_disconnect(self, client, userdata, *args):
        self._broker_connected = False
        log.warning("Broker connection lost; auto-reconnect in progress")

    def _on_message(self, client, userdata, msg):
        try:
            if msg.topic != TAGS_TOPIC:
                return  # message on an unexpected topic: ignore
            raw = parse_payload(msg.payload)
            with self._lock:
                stale_before = self._is_stale_locked()
                if self._baseline or stale_before:
                    self._baseline = True  # gap: re-baseline, never count across it
                events = [] if self._baseline else detect_events(self._previous_raw, raw)
                self._baseline = False
                self._previous_raw = raw
                self._raw = raw
                self._timestamp = datetime.now(timezone.utc).isoformat()
                self._last_recv = time.monotonic()
            for event in events:
                try:
                    if self._on_event is not None:
                        self._on_event(event)
                        log.info("Recorded event %s for broker %s", event, self.broker)
                except Exception:
                    log.exception("Failed to record event %s", event)
        except ValueError as exc:
            log.warning("Discarding malformed payload on %s: %s", msg.topic, exc)

    # -- state ---------------------------------------------------------------

    def _is_stale_locked(self) -> bool:
        if self._last_recv is None:
            return True
        return (time.monotonic() - self._last_recv) * 1000 > self._staleness_ms

    @property
    def broker(self) -> str:
        return f"{self._broker[0]}:{self._broker[1]}"

    @property
    def source(self) -> str:
        return "mqtt"

    def snapshot(self) -> dict:
        with self._lock:
            stale = self._is_stale_locked()
            return {
                "connected": self._broker_connected and self._raw is not None,
                "stale": stale,
                "connecting": self._raw is None,
                "server_time": datetime.now(timezone.utc).isoformat(),
                "last_update": self._timestamp,
                "values": build_view(self._raw) if self._raw is not None else None,
                "raw": dict(self._raw) if self._raw is not None else None,
                "broker": self.broker,
                "source": "mqtt",
            }
