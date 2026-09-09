import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

IDEAL_CYCLE_TIME_DEFAULT_S = 5.0
IDEAL_CYCLE_TIME_MIN_S = 0.1
IDEAL_CYCLE_TIME_MAX_S = 3600.0
WRITE_INTERVAL_DEFAULT_S = 1.0


@dataclass(frozen=True)
class RecorderConfig:
    oee_database_url: str
    write_interval_s: float
    ideal_cycle_time_s: float
    plc_ip: str
    plc_rack: int
    plc_slot: int
    poll_interval_ms: int


@dataclass(frozen=True)
class Config:
    plc_ip: str
    plc_rack: int
    plc_slot: int
    poll_interval_ms: int
    host: str
    port: int
    data_source: str = "direct"
    broker_host: str = "127.0.0.1"
    broker_port: int = 1883
    # Optional: used only by the MCP server's get_latest_oee tool. The
    # dashboard itself never requires a database (fail-fast is unchanged).
    oee_database_url: str | None = None


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable '{name}'. "
            f"Copy .env.example to .env and fill in the values."
        )
    return value


def load_config() -> Config:
    data_source = os.environ.get("DATA_SOURCE", "direct").strip().lower()
    if data_source not in ("direct", "mqtt"):
        raise ValueError("DATA_SOURCE must be 'direct' or 'mqtt'")

    # The MQTT broker address is typed by the user in the dashboard at
    # runtime; only DATA_SOURCE and the line-PC publisher's own broker
    # endpoint (BROKER_HOST/BROKER_PORT) come from configuration.
    return Config(
        plc_ip=_require("PLC_IP"),
        plc_rack=int(_require("PLC_RACK")),
        plc_slot=int(_require("PLC_SLOT")),
        poll_interval_ms=int(_require("POLL_INTERVAL_MS")),
        host=_require("HOST"),
        port=int(_require("PORT")),
        data_source=data_source,
        broker_host=os.environ.get("BROKER_HOST", "127.0.0.1"),
        broker_port=int(os.environ.get("BROKER_PORT", "1883")),
        oee_database_url=os.environ.get("OEE_DATABASE_URL") or None,
    )


def load_recorder_config() -> RecorderConfig:
    """Fail-fast config for the standalone OEE recorder.

    Requires only the recorder's own variables plus the shared PLC
    connection; never the dashboard's HOST/PORT.
    """
    ideal_raw = os.environ.get("IDEAL_CYCLE_TIME_S")
    ideal = float(ideal_raw) if ideal_raw else IDEAL_CYCLE_TIME_DEFAULT_S
    if not (IDEAL_CYCLE_TIME_MIN_S <= ideal <= IDEAL_CYCLE_TIME_MAX_S):
        raise ValueError(
            f"IDEAL_CYCLE_TIME_S must be between "
            f"{IDEAL_CYCLE_TIME_MIN_S} and {IDEAL_CYCLE_TIME_MAX_S} seconds"
        )
    interval_raw = os.environ.get("OEE_WRITE_INTERVAL_S")
    interval = float(interval_raw) if interval_raw else WRITE_INTERVAL_DEFAULT_S
    if interval <= 0:
        raise ValueError("OEE_WRITE_INTERVAL_S must be positive")
    return RecorderConfig(
        oee_database_url=_require("OEE_DATABASE_URL"),
        write_interval_s=interval,
        ideal_cycle_time_s=ideal,
        plc_ip=_require("PLC_IP"),
        plc_rack=int(_require("PLC_RACK")),
        plc_slot=int(_require("PLC_SLOT")),
        poll_interval_ms=int(_require("POLL_INTERVAL_MS")),
    )
