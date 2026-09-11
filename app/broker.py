import logging

from amqtt.broker import Broker

log = logging.getLogger(__name__)


def create_broker(port: int) -> Broker:
    """Plain, no-auth MQTT broker bound to 0.0.0.0:<port>."""
    log.info("Starting MQTT broker on 0.0.0.0:%s (anonymous, no TLS)", port)
    return Broker({
        "listeners": {"default": {"type": "tcp", "bind": f"0.0.0.0:{port}", "max_connections": 100}},
        "sys_interval": 10,
        "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
        "topic-check": {"enabled": False},
    })
