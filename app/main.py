import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import load_config
from app.db import ensure_schema, per_minute_counts
from app.source_manager import SOURCES, SourceManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

config = load_config()
STATIC_DIR = Path(__file__).resolve().parent / "static"

# `DATA_SOURCE` picks the startup source; the active source is switchable
# at runtime via POST /api/source (direct = the dashboard's own PLC only).
poller = SourceManager(config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema(config.database_url, default_line_ip=config.plc_ip)
    poller.start()
    log.info(
        "Source manager started: source=%s line=%s every %sms",
        poller.source,
        poller.line_ip or config.plc_ip,
        config.poll_interval_ms,
    )
    yield
    poller.stop()


app = FastAPI(title="PLC Conveyor Dashboard", lifespan=lifespan)


@app.get("/api/state")
def get_state():
    return poller.snapshot()


class LineSelection(BaseModel):
    line_ip: str


@app.post("/api/line")
def select_line(selection: LineSelection):
    if poller.source != "mqtt":
        raise HTTPException(status_code=400, detail="line switching requires the mqtt source")
    if config.lines and selection.line_ip not in config.lines:
        raise HTTPException(status_code=404, detail=f"unknown line '{selection.line_ip}'")
    try:
        poller.set_line(selection.line_ip)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return poller.snapshot()


class SourceSelection(BaseModel):
    source: str
    line_ip: str | None = None


@app.post("/api/source")
def select_source(selection: SourceSelection):
    if selection.source not in SOURCES:
        raise HTTPException(status_code=400, detail="source must be 'direct' or 'mqtt'")
    if (
        selection.line_ip is not None
        and selection.source == "mqtt"
        and config.lines
        and selection.line_ip not in config.lines
    ):
        raise HTTPException(status_code=404, detail=f"unknown line '{selection.line_ip}'")
    try:
        return poller.switch(selection.source, line_ip=selection.line_ip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/stats")
def get_stats(line_ip: str | None = None):
    try:
        selected = line_ip or getattr(poller, "line_ip", None) or ""
        return {
            "window_minutes": 10,
            "line_ip": selected,
            "points": per_minute_counts(config.database_url, window_minutes=10, line_ip=selected),
        }
    except Exception:
        log.exception("Failed to load statistics")
        raise HTTPException(status_code=503, detail="statistics unavailable")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
