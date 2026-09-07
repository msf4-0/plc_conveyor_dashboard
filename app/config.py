import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    plc_ip: str
    plc_rack: int
    plc_slot: int
    poll_interval_ms: int
    database_url: str
    host: str
    port: int
    data_source: str = "direct"
    mqtt_broker_host: str = "127.0.0.1"
    mqtt_broker_port: int = 1883
    broker_host: str = "127.0.0.1"
    broker_port: int = 1883
    lines: dict[str, tuple[str, int]] | None = None


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable '{name}'. "
            f"Copy .env.example to .env and fill in the values."
        )
    return value


def _parse_lines(raw: str) -> dict[str, tuple[str, int]]:
    """Parse LINES registry: 'PLC_IP=broker_host:port,PLC_IP=broker_host:port'."""
    lines: dict[str, tuple[str, int]] = {}
    for entry in filter(None, (e.strip() for e in raw.split(","))):
        line_ip, _, endpoint = entry.partition("=")
        line_ip, endpoint = line_ip.strip(), endpoint.strip()
        host, sep, port = endpoint.rpartition(":")
        if not sep or not host or not port.isdigit():
            raise ValueError(f"LINES entry '{entry}' must be PLC_IP=host:port")
        if line_ip in lines:
            raise ValueError(f"LINES lists PLC_IP '{line_ip}' more than once")
        lines[line_ip] = (host, int(port))
    return lines


def load_config() -> Config:
    data_source = os.environ.get("DATA_SOURCE", "direct").strip().lower()
    if data_source not in ("direct", "mqtt"):
        raise ValueError("DATA_SOURCE must be 'direct' or 'mqtt'")

    lines_raw = os.environ.get("LINES", "")
    lines = _parse_lines(lines_raw) if lines_raw.strip() else None

    # MQTT_BROKER_* defaults to the first registry line's endpoint; required
    # (or settable) only when MQTT mode has no registry to fall back on.
    if data_source == "mqtt" or lines:
        if lines:
            first_host, first_port = next(iter(lines.values()))
            mqtt_broker_host = os.environ.get("MQTT_BROKER_HOST", first_host)
            mqtt_broker_port = int(os.environ.get("MQTT_BROKER_PORT", str(first_port)))
        else:
            mqtt_broker_host = _require("MQTT_BROKER_HOST")
            mqtt_broker_port = int(_require("MQTT_BROKER_PORT"))
    else:
        mqtt_broker_host, mqtt_broker_port = "127.0.0.1", 1883

    return Config(
        plc_ip=_require("PLC_IP"),
        plc_rack=int(_require("PLC_RACK")),
        plc_slot=int(_require("PLC_SLOT")),
        poll_interval_ms=int(_require("POLL_INTERVAL_MS")),
        database_url=_require("DATABASE_URL"),
        host=_require("HOST"),
        port=int(_require("PORT")),
        data_source=data_source,
        mqtt_broker_host=mqtt_broker_host,
        mqtt_broker_port=mqtt_broker_port,
        broker_host=os.environ.get("BROKER_HOST", "127.0.0.1"),
        broker_port=int(os.environ.get("BROKER_PORT", "1883")),
        lines=lines,
    )
