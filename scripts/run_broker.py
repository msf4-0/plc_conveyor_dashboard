"""Run the line-PC MQTT broker (no auth) on BROKER_PORT (default 1883).

Usage: .\\.venv\\Scripts\\python.exe scripts\\run_broker.py
Stop with Ctrl+C; the broker shuts down cleanly.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.broker import start_broker, stop_broker
from app.config import load_config


async def main() -> None:
    port = load_config().broker_port
    broker = await start_broker(port)
    print(f"MQTT broker listening on 0.0.0.0:{port} — press Ctrl+C to stop")
    try:
        await asyncio.Event().wait()  # run until interrupted
    finally:
        await stop_broker(broker)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
