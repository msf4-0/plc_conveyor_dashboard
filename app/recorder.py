"""Standalone OEE recorder: polls the directly-connected PLC over snap7,
computes OEE with the simplified engine, and appends history rows to the
local `oee` PostgreSQL database — regardless of what the dashboard does.

Run with: python -m app.recorder
"""

import logging
import time
from datetime import datetime, timezone

from app.config import RecorderConfig, load_recorder_config
from app.db import ensure_oee_schema, insert_oee_row
from app.oee import OeeEngine
from app.plc import Snap7Reader
from app.tags import raw_values

log = logging.getLogger(__name__)


class OeeRecorder:
    """Poll + persist loop for one directly-connected PLC.

    `poll_once` reads the PLC and feeds the engine (re-baselining on comms
    failure); `maybe_write` appends a history row when the write interval
    has elapsed and the PLC is connected. Database insert failures are
    logged and never stop recording.
    """

    def __init__(
        self,
        reader,
        dsn: str,
        poll_interval_s: float,
        write_interval_s: float,
        engine: OeeEngine,
        insert_row=insert_oee_row,
        now_fn=time.monotonic,
    ):
        self._reader = reader
        self._dsn = dsn
        self._poll_interval = poll_interval_s
        self._write_interval = write_interval_s
        self._engine = engine
        self._insert_row = insert_row
        self._now = now_fn
        self._connected = False
        self._last_write = float("-inf")

    @property
    def connected(self) -> bool:
        return self._connected

    def poll_once(self) -> bool:
        """One PLC read + engine feed; returns True when connected."""
        try:
            if not self._connected:
                self._reader.connect()
            inputs, outputs = self._reader.read()
            self._engine.on_snapshot(raw_values(inputs, outputs), self._now())
            self._connected = True
            return True
        except Exception:
            if self._connected:
                log.exception("PLC communication failed; pausing OEE recording")
            self._connected = False
            self._engine.on_disconnect()  # pause; next snapshot re-baselines
            try:
                self._reader.close()
            except Exception:
                log.exception("Error while closing PLC connection")
            return False

    def maybe_write(self) -> bool:
        """Insert a history row if the write interval elapsed; returns whether
        a row was written. Rows are only written while connected so the
        disconnected period is not filled with frozen duplicates."""
        now = self._now()
        if not self._connected or now - self._last_write < self._write_interval:
            return False
        metrics = self._engine.metrics()
        try:
            self._insert_row(
                self._dsn,
                metrics["availability"],
                metrics["performance"],
                metrics["quality"],
                metrics["oee"],
            )
        except Exception:
            log.exception("Failed to persist OEE row; recording continues")
            return False
        self._last_write = now
        log.info(
            "Recorded OEE row at %s: A=%s P=%s Q=%s OEE=%s",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            metrics["availability"],
            metrics["performance"],
            metrics["quality"],
            metrics["oee"],
        )
        return True

    def run(self) -> None:
        """Blocking loop: poll the PLC, write rows, sleep out the interval."""
        while True:
            self.poll_once()
            self.maybe_write()
            time.sleep(self._poll_interval)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    cfg: RecorderConfig = load_recorder_config()
    engine = OeeEngine(ideal_cycle_time_s=cfg.ideal_cycle_time_s)
    ensure_oee_schema(cfg.oee_database_url)
    reader = Snap7Reader(cfg.plc_ip, cfg.plc_rack, cfg.plc_slot)
    recorder = OeeRecorder(
        reader=reader,
        dsn=cfg.oee_database_url,
        poll_interval_s=cfg.poll_interval_ms / 1000.0,
        write_interval_s=cfg.write_interval_s,
        engine=engine,
    )
    log.info(
        "OEE recorder started: PLC %s -> %s every %ss (write every %ss, ideal CT %ss)",
        cfg.plc_ip,
        cfg.oee_database_url.rpartition("/")[2],
        cfg.poll_interval_ms / 1000.0,
        cfg.write_interval_s,
        cfg.ideal_cycle_time_s,
    )
    recorder.run()


if __name__ == "__main__":
    main()
