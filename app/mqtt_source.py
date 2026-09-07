import logging
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from app.db import insert_event
from app.edges import detect_events
from app.mqtt_proto import parse_snapshot, state_topic, status_topic
from app.plc import build_view
from app.tags import raw_values

log = logging.getLogger(__name__)

DEFAULT_STALENESS_MS = 2000  # ~4 poll intervals at 500 ms


def make_paho_client() -> mqtt.Client:
    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


class MqttLineSource:
    """Dashboard-side subscriber for one MQTT line at a time.

    Mirrors PlcPoller.snapshot(): decodes raw I/Q bytes with the shared tag
    map, detects P3/B4 rising edges (baseline-only on connect/switch/stale
    resume) and persists events with the line's IP. Liveness: stale while the
    line's status topic says `offline` or no snapshot for `staleness_ms`.
    """

    def __init__(
        self,
        broker_host: str,
        broker_port: int,
        dsn: str,
        poll_interval_ms: int,
        line_ip: str | None = None,
        lines: dict[str, tuple[str, int]] | None = None,
        staleness_ms: int = DEFAULT_STALENESS_MS,
        client_factory=make_paho_client,
    ):
        self._broker = (broker_host, broker_port)
        self._dsn = dsn
        self._staleness_ms = staleness_ms
        self._lines = dict(lines or {})
        self._lock = threading.Lock()
        self._line_ip = line_ip or (next(iter(self._lines), None))
        self._broker_connected = False
        self._raw: dict[str, bool] | None = None
        self._previous_raw: dict[str, bool] | None = None
        self._baseline = True  # first snapshot after connect/switch/stale: no events
        self._status_online: bool | None = None
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

    def set_line(self, line_ip: str) -> None:
        if self._lines and line_ip not in self._lines:
            raise ValueError(f"unknown line '{line_ip}'")
        with self._lock:
            previous_ip = self._line_ip
            self._line_ip = line_ip
            self._raw = None
            self._previous_raw = None
            self._baseline = True
            self._status_online = None
            self._last_recv = None
            self._timestamp = None
        try:
            if previous_ip is not None and previous_ip != line_ip:
                self._client.unsubscribe(
                    [state_topic(previous_ip), status_topic(previous_ip)]
                )
            self._client.subscribe([(state_topic(line_ip), 0), (status_topic(line_ip), 0)])
        except Exception:
            # offline right now: on_connect resubscribes the current line
            log.exception("Resubscribe failed; will retry on reconnect")

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
        client.subscribe([(state_topic(self._line_ip), 0), (status_topic(self._line_ip), 0)])

    def _on_disconnect(self, client, userdata, *args):
        self._broker_connected = False
        log.warning("Broker connection lost; auto-reconnect in progress")

    def _on_message(self, client, userdata, msg):
        try:
            if msg.topic == status_topic(self._line_ip):
                status = msg.payload.decode("utf-8", "replace").strip().lower()
                with self._lock:
                    self._status_online = status == "online"
                return
            if msg.topic != state_topic(self._line_ip):
                return  # message from another line: ignore
            snap = parse_snapshot(msg.payload)
            raw = raw_values(snap["inputs"], snap["outputs"])
            with self._lock:
                stale_before = self._is_stale_locked()
                if stale_before:
                    self._baseline = True  # gap: re-baseline, never count across it
                events = [] if self._baseline else detect_events(self._previous_raw, raw)
                self._baseline = False
                self._previous_raw = raw
                self._raw = raw
                self._timestamp = snap["ts"]
                self._last_recv = time.monotonic()
                self._status_online = True  # fresh snapshots imply a live publisher
            for event in events:
                try:
                    insert_event(self._dsn, event, line_ip=self._line_ip)
                    log.info("Recorded event %s for line %s", event, self._line_ip)
                except Exception:
                    log.exception("Failed to persist event %s", event)
        except ValueError as exc:
            log.warning("Discarding malformed snapshot on %s: %s", msg.topic, exc)

    # -- state ---------------------------------------------------------------

    def _is_stale_locked(self) -> bool:
        if self._status_online is False:
            return True
        if self._last_recv is None:
            return True
        return (time.monotonic() - self._last_recv) * 1000 > self._staleness_ms

    @property
    def line_ip(self) -> str | None:
        return self._line_ip

    @property
    def source(self) -> str:
        return "mqtt"

    @property
    def lines(self) -> dict[str, tuple[str, int]]:
        return dict(self._lines)

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
                "line_ip": self._line_ip,
                "source": "mqtt",
                "lines": {ip: f"{host}:{port}" for ip, (host, port) in self._lines.items()},
            }
