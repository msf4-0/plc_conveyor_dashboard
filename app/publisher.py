"""Line-PC publisher: reads the PLC process image read-only and publishes the
tag booleans over MQTT to the local broker on the fixed topic `plc_tags`.

Run on the PC next to each PLC:
    .\\.venv\\Scripts\\python.exe -m app.publisher

Env (same .env layout as the dashboard): PLC_IP, PLC_RACK, PLC_SLOT,
POLL_INTERVAL_MS, BROKER_HOST (default 127.0.0.1), BROKER_PORT (default 1883).
"""

import logging
import threading
import time

import paho.mqtt.client as mqtt

from app.config import load_config
from app.mqtt_proto import TAGS_TOPIC, encode_payload
from app.plc import Snap7Reader
from app.tags import raw_values

log = logging.getLogger(__name__)


class LinePublisher:
    """Publishes tag-boolean snapshots to `plc_tags` at the poll interval.

    No retain flag and no status publishing: liveness is judged by the
    dashboard from packet cadence alone. PLC access stays strictly read-only.
    """

    def __init__(
        self,
        reader: Snap7Reader,
        broker_host: str,
        broker_port: int,
        poll_interval_ms: int,
    ):
        self._reader = reader
        self._poll_interval = poll_interval_ms / 1000.0
        self._stop = threading.Event()
        self._thread = None
        self._mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._mqtt.on_connect = self._on_connect
        self._broker = (broker_host, broker_port)

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self._mqtt.connect(*self._broker)
        self._mqtt.loop_start()
        self._thread = threading.Thread(target=self._run, name="line-publisher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        try:
            self._mqtt.disconnect()
            self._mqtt.loop_stop()
        except Exception:
            log.exception("Error while disconnecting from broker")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        log.info("Connected to broker %s:%s", *self._broker)

    # -- loop ---------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._reader.connect()
                inputs, outputs = self._reader.read()
                self._mqtt.publish(
                    TAGS_TOPIC,
                    encode_payload(raw_values(inputs, outputs)),
                    qos=0,
                )
            except Exception:
                log.exception("PLC read failed; will retry")
                self._reader.close()
            time.sleep(self._poll_interval)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = load_config()
    reader = Snap7Reader(cfg.plc_ip, cfg.plc_rack, cfg.plc_slot)
    publisher = LinePublisher(
        reader=reader,
        broker_host=cfg.broker_host,
        broker_port=cfg.broker_port,
        poll_interval_ms=cfg.poll_interval_ms,
    )
    publisher.start()
    log.info(
        "Publisher started: PLC %s -> broker %s:%s every %sms (topic %s)",
        cfg.plc_ip, cfg.broker_host, cfg.broker_port, cfg.poll_interval_ms, TAGS_TOPIC,
    )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        publisher.stop()
        reader.close()


if __name__ == "__main__":
    main()
