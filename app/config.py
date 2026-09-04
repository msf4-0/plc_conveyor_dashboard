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


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable '{name}'. "
            f"Copy .env.example to .env and fill in the values."
        )
    return value


def load_config() -> Config:
    return Config(
        plc_ip=_require("PLC_IP"),
        plc_rack=int(_require("PLC_RACK")),
        plc_slot=int(_require("PLC_SLOT")),
        poll_interval_ms=int(_require("POLL_INTERVAL_MS")),
        database_url=_require("DATABASE_URL"),
        host=_require("HOST"),
        port=int(_require("PORT")),
    )
