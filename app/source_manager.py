import logging
from collections.abc import Callable
from datetime import datetime, timezone

from app.config import Config
from app.mqtt_source import MqttLineSource
from app.plc import PlcPoller, Snap7Reader

log = logging.getLogger(__name__)

SOURCES = ("direct", "mqtt")


class InactiveMqttSource:
    """Placeholder for the MQTT slot before a broker address is submitted.

    Startup `DATA_SOURCE=mqtt` without a typed broker address lands here:
    the slot exists but connects nowhere and reports a connecting snapshot.
    """

    source = "mqtt"
    broker = None

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def snapshot(self) -> dict:
        return {
            "connected": False,
            "stale": False,
            "connecting": True,
            "server_time": datetime.now(timezone.utc).isoformat(),
            "last_update": None,
            "values": None,
            "broker": None,
            "source": "mqtt",
        }


def build_source(
    config: Config,
    name: str,
    broker: tuple[str, int] | None = None,
    on_event: Callable[[str], None] | None = None,
):
    """Construct a data source from the existing configuration.

    `direct` is always the dashboard's own configured PLC.
    `mqtt` connects to the given broker address (host, port); `broker=None`
    yields the inactive MQTT slot that connects until an address is submitted.
    Edge events are delivered to `on_event` (the dashboard's counter).
    """
    if name not in SOURCES:
        raise ValueError(f"unknown data source '{name}' (expected 'direct' or 'mqtt')")
    if name == "mqtt":
        if broker is None:
            return InactiveMqttSource()
        host, port = broker
        return MqttLineSource(
            broker_host=host,
            broker_port=port,
            on_event=on_event,
        )
    return PlcPoller(
        reader=Snap7Reader(config.plc_ip, config.plc_rack, config.plc_slot),
        poll_interval_ms=config.poll_interval_ms,
        line_ip=config.plc_ip,
        on_event=on_event,
    )


class SourceManager:
    """Owns the active data source and switches between them at runtime.

    `DATA_SOURCE` only chooses the startup source. A switch builds a fresh
    source (which re-baselines its first snapshot, preserving the
    no-phantom-count invariant); a failed build/start leaves the previous
    source running. Switching to `mqtt` requires a broker address, and
    submitting a different address while `mqtt` is active rebuilds the source.
    `on_event` receives edge events from the active source;
    `on_connection_change` fires after a successful source or broker switch so
    the dashboard can reset its per-minute counters.
    """

    def _build(self, name: str, broker: tuple[str, int] | None = None):
        kwargs = {"on_event": self._on_event}
        if name == "mqtt" and broker is not None:
            kwargs["broker"] = broker
        return self._factory(self._config, name, **kwargs)

    def __init__(self, config: Config, initial_source: str | None = None,
                 on_event: Callable[[str], None] | None = None,
                 on_connection_change: Callable[[], None] | None = None,
                 factory=build_source):
        self._config = config
        self._factory = factory
        self._on_event = on_event
        self._on_connection_change = on_connection_change
        name = initial_source or config.data_source
        if name not in SOURCES:
            raise ValueError(f"unknown data source '{name}' (expected 'direct' or 'mqtt')")
        self._source = self._build(name)
        self._source_name = name
        self._active_broker: tuple[str, int] | None = (
            self._broker_of(self._source) if name == "mqtt" else None
        )

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self._source.start()

    def stop(self) -> None:
        self._source.stop()

    def switch(self, source_name: str, broker: tuple[str, int] | None = None) -> dict:
        """Activate another source; returns the new source's snapshot."""
        if source_name not in SOURCES:
            raise ValueError(f"unknown data source '{source_name}' (expected 'direct' or 'mqtt')")
        if source_name == "mqtt":
            if broker is None:
                raise ValueError("a broker address is required for the mqtt source")
            if source_name == self._source_name and broker == self._active_broker:
                return self._source.snapshot()  # same broker: idempotent no-op
        elif source_name == self._source_name:
            return self._source.snapshot()  # same source: idempotent no-op
        new_source = self._build(source_name, broker)
        try:
            new_source.start()
        except Exception:
            log.exception("Failed to start %s source; keeping %s", source_name, self._source_name)
            raise  # old source still running
        self._source.stop()
        self._source = new_source
        self._source_name = source_name
        self._active_broker = broker if source_name == "mqtt" else None
        self._fire_connection_change()
        log.info("Switched data source to %s (connection %s)", source_name, self.connection)
        return self._source.snapshot()

    def _fire_connection_change(self) -> None:
        if self._on_connection_change is None:
            return
        try:
            self._on_connection_change()
        except Exception:
            log.exception("Connection-change callback failed")

    # -- delegation ---------------------------------------------------------

    def snapshot(self) -> dict:
        return self._source.snapshot()

    # -- state --------------------------------------------------------------

    @staticmethod
    def _broker_of(source) -> tuple[str, int] | None:
        # MqttLineSource owns (host, port) but only exposes the "host:port"
        # string; recover the tuple from the paho client's connect target.
        return getattr(source, "_broker", None)

    @property
    def source(self) -> str:
        return self._source_name

    @property
    def connection(self) -> str | None:
        """Identity of the active connection: the typed broker address in
        `mqtt` mode, the configured PLC IP in `direct` mode."""
        return getattr(self._source, "broker", None) or getattr(self._source, "line_ip", None)
