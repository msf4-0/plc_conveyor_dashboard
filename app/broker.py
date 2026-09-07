import logging

from amqtt.broker import Broker

log = logging.getLogger(__name__)

BROKER_CONFIG = {
    "listeners": {
        "default": {"type": "tcp", "bind": "0.0.0.0:{port}", "max_connections": 100},
    },
    "sys_interval": 10,
    "auth": {
        "allow-anonymous": True,
        "plugins": ["auth_anonymous"],
    },
    "topic-check": {"enabled": False},
}


def create_broker(port: int) -> Broker:
    """Plain, no-auth MQTT broker bound to 0.0.0.0:<port>."""
    config = {
        "listeners": {
            "default": dict(BROKER_CONFIG["listeners"]["default"], bind=f"0.0.0.0:{port}")
        },
        "sys_interval": BROKER_CONFIG["sys_interval"],
        "auth": dict(BROKER_CONFIG["auth"]),
        "topic-check": dict(BROKER_CONFIG["topic-check"]),
    }
    log.info("Starting MQTT broker on 0.0.0.0:%s (anonymous, no TLS)", port)
    return Broker(config)


async def start_broker(port: int) -> Broker:
    broker = create_broker(port)
    await broker.start()
    return broker


async def stop_broker(broker: Broker) -> None:
    await broker.shutdown()
    log.info("MQTT broker stopped")
