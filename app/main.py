import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import load_config
from app.db import (
    latest_oee_row,
    oee_history,
    test_oee_connection,
)
from app.mcp_server import create_mcp_server
from app.source_manager import SOURCES, SourceManager
from app.stats import MinuteCounter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

config = load_config()
STATIC_DIR = Path(__file__).resolve().parent / "static"

# `DATA_SOURCE` picks the startup source; the active source is switchable
# at runtime via POST /api/source (direct = the dashboard's own PLC only).
# OEE figures are NOT computed here: they are recorded per-line by the
# standalone recorder process (python -m app.recorder) into each line's
# local `oee` database, which this dashboard reads on demand (see the
# /api/oee* endpoints below).
# Per-minute cycle/metal counts are owned by this process (in-memory,
# reset on restart and on connection change) - nothing is persisted.
counter = MinuteCounter()
poller = SourceManager(
    config, on_event=counter.record, on_connection_change=counter.reset
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    poller.start()
    log.info(
        "Source manager started: source=%s connection=%s every %sms",
        poller.source,
        poller.connection,
        config.poll_interval_ms,
    )
    # Mounted sub-app lifespans don't run in Starlette: run the MCP streamable
    # HTTP session manager for the serving period ourselves.
    async with mcp_server.session_manager.run():
        yield
    poller.stop()


app = FastAPI(title="PLC Conveyor Dashboard", lifespan=lifespan)

# MCP server (read-only tools for chatbots / n8n MCP Client Tool): Streamable
# HTTP transport at /mcp, same process and port as the dashboard.
# get_iq_data reads the live source manager; get_latest_oee reads
# OEE_DATABASE_URL directly (independent of the UI-connected OEE database).
# Building the ASGI app initializes the session manager used in lifespan.
mcp_server = create_mcp_server(
    snapshot_fn=poller.snapshot, oee_database_url=config.oee_database_url
)
mcp_asgi = mcp_server.streamable_http_app()


@app.get("/api/state")
def get_state():
    return poller.snapshot()


def _parse_broker(broker: str) -> tuple[str, int]:
    """Parse a user-typed broker address 'IP' or 'IP:port' (default 1883)."""
    text = broker.strip()
    if not text:
        raise ValueError("broker address is required")
    host, sep, port = text.rpartition(":")
    if not sep:
        return text, 1883
    if not host or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError(f"invalid broker address '{text}' (expected IP or IP:port)")
    return host, int(port)


class SourceSelection(BaseModel):
    source: str
    broker: str | None = None


@app.post("/api/source")
def select_source(selection: SourceSelection):
    if selection.source not in SOURCES:
        raise HTTPException(status_code=400, detail="source must be 'direct' or 'mqtt'")
    broker: tuple[str, int] | None = None
    if selection.source == "mqtt":
        if not selection.broker:
            raise HTTPException(
                status_code=400,
                detail="a broker address (IP or IP:port) is required for the mqtt source",
            )
        try:
            broker = _parse_broker(selection.broker)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    try:
        result = poller.switch(selection.source, broker=broker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


# -- OEE display (database-backed; figures come from the per-line recorder) --

class OeeConnection(BaseModel):
    ip: str
    port: int
    user: str
    password: str


# One active OEE database connection at a time (single-user dashboard).
_oee_conn: dict = {"dsn": None, "ip": None, "port": None}


def _build_oee_dsn(conn: OeeConnection) -> str:
    user = quote(conn.user, safe="")
    password = quote(conn.password, safe="")
    return f"postgresql://{user}:{password}@{conn.ip}:{conn.port}/oee"


@app.post("/api/oee/connection")
def connect_oee(conn: OeeConnection):
    """Test a connection to a line's `oee` database; on success it becomes
    the active OEE data source. A failure leaves the previous state intact."""
    dsn = _build_oee_dsn(conn)
    try:
        test_oee_connection(dsn)
    except Exception:
        log.exception("OEE database connection failed for %s:%s", conn.ip, conn.port)
        raise HTTPException(
            status_code=502,
            detail=f"could not connect to the oee database at {conn.ip}:{conn.port}",
        )
    _oee_conn.update(dsn=dsn, ip=conn.ip, port=conn.port)
    log.info("OEE display connected to %s:%s", conn.ip, conn.port)
    return {"connected": True, "ip": conn.ip, "port": conn.port}


@app.get("/api/oee")
def get_oee():
    """Latest OEE row from the connected database (or an error payload)."""
    empty = {
        "timestamp": None,
        "availability": None,
        "performance": None,
        "quality": None,
        "oee": None,
    }
    dsn = _oee_conn["dsn"]
    if dsn is None:
        return {"connected": False, "error": "not connected to an OEE database", **empty}
    try:
        row = latest_oee_row(dsn)
    except Exception:
        log.exception("Failed to read the latest OEE row")
        return {"connected": False, "error": "OEE database unreachable", **empty}
    if row is None:
        return {"connected": True, "error": "no OEE data recorded yet", **empty}
    return {"connected": True, "error": None, **row}


@app.get("/api/oee/history")
def get_oee_history(minutes: int = 10):
    if not 1 <= minutes <= 1440:
        raise HTTPException(status_code=400, detail="minutes must be between 1 and 1440")
    dsn = _oee_conn["dsn"]
    if dsn is None:
        return {"minutes": minutes, "points": []}
    try:
        return {"minutes": minutes, "points": oee_history(dsn, minutes)}
    except Exception:
        log.exception("Failed to read OEE history")
        raise HTTPException(status_code=503, detail="OEE history unavailable")


@app.get("/api/stats")
def get_stats():
    """Per-minute counts for the active connection, from the in-process
    counter. Counts are process-local and reset whenever the active source
    or broker address changes."""
    return {
        "window_minutes": 10,
        "connection": poller.connection,
        "points": counter.snapshot(window_minutes=10),
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# MCP last: mounted at "/" so the sub-app's single route serves exactly /mcp
# without shadowing the dashboard or /api/* routes registered above.
app.mount("/", mcp_asgi)
