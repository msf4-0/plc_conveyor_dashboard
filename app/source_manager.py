import logging

from app.config import Config
from app.mqtt_source import MqttLineSource
from app.plc import PlcPoller, Snap7Reader

log = logging.getLogger(__name__)

SOURCES = ("direct", "mqtt")


def build_source(config: Config, name: str, line_ip: str | None = None):
    """Construct a data source from the existing configuration.

    `direct` is always the dashboard's own configured PLC (Option A).
    `mqtt` connects to the selected line's registry endpoint when the line is
    registered, falling back to the configured broker address otherwise.
    """
    if name not in SOURCES:
        raise ValueError(f"unknown data source '{name}' (expected 'direct' or 'mqtt')")
    if name == "mqtt":
        lines = config.lines or {}
        default_line = next(iter(lines), config.plc_ip) if lines else config.plc_ip
        selected = line_ip or default_line
        if selected in lines:
            host, port = lines[selected]
        else:
            host, port = config.mqtt_broker_host, config.mqtt_broker_port
        return MqttLineSource(
            broker_host=host,
            broker_port=port,
            dsn=config.database_url,
            poll_interval_ms=config.poll_interval_ms,
            line_ip=selected,
            lines=lines,
        )
    return PlcPoller(
        reader=Snap7Reader(config.plc_ip, config.plc_rack, config.plc_slot),
        dsn=config.database_url,
        poll_interval_ms=config.poll_interval_ms,
        line_ip=config.plc_ip,
    )


class SourceManager:
    """Owns the active data source and switches between them at runtime.

    `DATA_SOURCE` only chooses the startup source. A switch builds a fresh
    source (which re-baselines its first snapshot, preserving the
    no-phantom-count invariant); a failed build/start leaves the previous
    source running.
    """

    def __init__(self, config: Config, initial_source: str | None = None, factory=build_source):
        self._config = config
        self._factory = factory
        name = initial_source or config.data_source
        if name not in SOURCES:
            raise ValueError(f"unknown data source '{name}' (expected 'direct' or 'mqtt')")
        self._source = factory(config, name)
        self._source_name = name

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self._source.start()

    def stop(self) -> None:
        self._source.stop()

    def switch(self, source_name: str, line_ip: str | None = None) -> dict:
        """Activate another source; returns the new source's snapshot."""
        if source_name not in SOURCES:
            raise ValueError(f"unknown data source '{source_name}' (expected 'direct' or 'mqtt')")
        if source_name == self._source_name:
            return self._source.snapshot()  # idempotent no-op
        lines = self._config.lines or {}
        if line_ip is None:
            line_ip = next(iter(lines), self._config.plc_ip) if lines else self._config.plc_ip
        elif lines and line_ip not in lines:
            raise ValueError(f"unknown line '{line_ip}'")
        new_source = self._factory(self._config, source_name, line_ip)
        try:
            new_source.start()
        except Exception:
            log.exception("Failed to start %s source; keeping %s", source_name, self._source_name)
            raise  # old source still running
        self._source.stop()
        self._source = new_source
        self._source_name = source_name
        log.info("Switched data source to %s (line %s)", source_name, self.line_ip)
        return self._source.snapshot()

    # -- delegation ---------------------------------------------------------

    def snapshot(self) -> dict:
        return self._source.snapshot()

    def set_line(self, line_ip: str) -> None:
        if self._source_name != "mqtt":
            raise ValueError("line switching requires the mqtt source")
        self._source.set_line(line_ip)

    # -- state --------------------------------------------------------------

    @property
    def source(self) -> str:
        return self._source_name

    @property
    def line_ip(self) -> str | None:
        return getattr(self._source, "line_ip", None)

    @property
    def lines(self) -> dict:
        return getattr(self._source, "lines", {})
