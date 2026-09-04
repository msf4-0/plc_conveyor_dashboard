import logging
import threading
import time
from datetime import datetime, timezone

from app.db import insert_event
from app.edges import detect_events
from app.tags import TAGS, button_pressed, raw_values

log = logging.getLogger(__name__)


class Snap7Reader:
    """Reads the S7-1200 process image (inputs I0.0-I1.7, outputs Q0.0-Q1.7)."""

    def __init__(self, ip: str, rack: int, slot: int):
        self._ip = ip
        self._rack = rack
        self._slot = slot
        self._client = None

    def connect(self) -> None:
        import snap7
        from snap7 import Area  # noqa: F401  (used in read())

        self._client = snap7.client.Client()
        self._client.connect(self._ip, self._rack, self._slot)
        if not self._client.get_connected():
            raise ConnectionError(f"Could not connect to PLC at {self._ip}")

    def read(self) -> tuple[bytes, bytes]:
        from snap7 import Area

        inputs = bytes(self._client.read_area(Area.PE, 0, 0, 2))
        outputs = bytes(self._client.read_area(Area.PA, 0, 0, 2))
        return inputs, outputs

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.disconnect()
                self._client.destroy()
            except Exception:
                log.exception("Error while closing PLC connection")
            self._client = None


class PlcPoller:
    """Background poll loop: reads the process image, detects counter edges,
    persists events, and publishes the latest snapshot for the API.

    On connection loss the last values are frozen and `connected` goes False;
    on reconnect the first snapshot only re-baselines edge detection.
    """

    def __init__(self, reader, dsn: str, poll_interval_ms: int):
        self._reader = reader
        self._dsn = dsn
        self._poll_interval = poll_interval_ms / 1000.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._connected = False
        self._raw: dict[str, bool] | None = None
        self._previous_raw: dict[str, bool] | None = None
        self._timestamp: str | None = None

    # -- public API ---------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="plc-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "connected": self._connected,
                "stale": not self._connected,
                "server_time": datetime.now(timezone.utc).isoformat(),
                "last_update": self._timestamp,
                "values": build_view(self._raw) if self._raw is not None else None,
            }

    # -- loop ---------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if self._raw is None or not self._connected:
                    self._reader.connect()
                inputs, outputs = self._reader.read()
                self._process(raw_values(inputs, outputs))
                self._connected = True
            except Exception:
                if self._connected or self._raw is not None:
                    log.exception("PLC communication failed; marking stale")
                self._connected = False
                self._reader.close()
            time.sleep(self._poll_interval)

    def _process(self, raw: dict[str, bool]) -> None:
        events = detect_events(self._previous_raw, raw)
        self._previous_raw = raw
        for event in events:
            try:
                insert_event(self._dsn, event)
                log.info("Recorded event: %s", event)
            except Exception:
                log.exception("Failed to persist event %s", event)
        with self._lock:
            self._raw = raw
            self._timestamp = datetime.now(timezone.utc).isoformat()


BUTTON_ALIASES = [("e_stop", "ESO"), ("stop", "S1"), ("start", "S2"), ("reset", "S3")]
SENSOR_ALIASES = [("b1", "B1"), ("b2", "B2"), ("b3", "B3"), ("metal_detector", "B4")]


def build_view(raw: dict[str, bool] | None) -> dict | None:
    if raw is None:
        return None
    return {
        "lights": {
            "red": raw["P1"],
            "yellow": raw["P2"],
            "green": raw["P3"],
        },
        "buttons": {
            alias: {"name": name, "pressed": button_pressed(raw[name], TAGS[name])}
            for alias, name in BUTTON_ALIASES
        },
        "conveyor": {"running": raw["K1"]},
        "sensors": {
            alias: {"name": name, "detecting": raw[name]}
            for alias, name in SENSOR_ALIASES
        },
    }
