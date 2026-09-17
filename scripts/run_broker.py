"""Run the line-PC MQTT broker (shared-credential auth, plc_tags only) on
BROKER_PORT (default 1883).

Usage: .\\.venv\\Scripts\\python.exe scripts\\run_broker.py
Stop with Ctrl+C; the broker shuts down cleanly.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.broker import create_broker
from app.config import load_config


async def main() -> None:
    cfg = load_config()
    broker = create_broker(cfg.broker_port, cfg.mqtt_username, cfg.mqtt_password)
    await broker.start()
    print(f"MQTT broker listening on 0.0.0.0:{cfg.broker_port} — press Ctrl+C to stop")
    try:
        await asyncio.Event().wait()  # run until interrupted
    finally:
        await broker.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
