import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import load_config
from app.db import ensure_schema, per_minute_counts
from app.plc import PlcPoller, Snap7Reader

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

config = load_config()
STATIC_DIR = Path(__file__).resolve().parent / "static"

poller = PlcPoller(
    reader=Snap7Reader(config.plc_ip, config.plc_rack, config.plc_slot),
    dsn=config.database_url,
    poll_interval_ms=config.poll_interval_ms,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema(config.database_url)
    poller.start()
    log.info(
        "Poller started: PLC %s (rack %s, slot %s) every %sms",
        config.plc_ip,
        config.plc_rack,
        config.plc_slot,
        config.poll_interval_ms,
    )
    yield
    poller.stop()


app = FastAPI(title="PLC Conveyor Dashboard", lifespan=lifespan)


@app.get("/api/state")
def get_state():
    return poller.snapshot()


@app.get("/api/stats")
def get_stats():
    try:
        return {
            "window_minutes": 10,
            "points": per_minute_counts(config.database_url, window_minutes=10),
        }
    except Exception:
        log.exception("Failed to load statistics")
        raise HTTPException(status_code=503, detail="statistics unavailable")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
