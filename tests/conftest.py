import asyncio
import socket
import threading
import time

import pytest

from app.broker import start_broker, stop_broker


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class BrokerRunner:
    """Runs an in-process amqtt broker in a daemon thread."""

    def __init__(self):
        self.port = _free_port()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        async def go():
            broker = await start_broker(self.port)
            try:
                while not self._stop.is_set():
                    await asyncio.sleep(0.2)
            finally:
                await stop_broker(broker)

        asyncio.run(go())

    def __enter__(self):
        self._thread.start()
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return self
            except OSError:
                if not self._thread.is_alive():
                    raise RuntimeError("broker thread died at startup")
                time.sleep(0.1)
        raise RuntimeError("broker did not start within 10s")

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=10)


@pytest.fixture()
def mqtt_broker():
    with BrokerRunner() as runner:
        yield runner
