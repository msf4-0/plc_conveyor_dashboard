import logging
from pathlib import Path
import tempfile

from amqtt.broker import Broker
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

log = logging.getLogger(__name__)


def create_broker(port: int, username: str, password: str) -> Broker:
    """Password-authenticated broker locked to the single `plc_tags` topic.

    Rejects anonymous connections: a client must present the shared
    credential (MQTT_USERNAME / MQTT_PASSWORD from .env). amqtt's
    FileAuthPlugin reads a password file that holds only the credential's
    argon2 hash (never the plaintext). The topic ACL allows publish and
    subscribe on `plc_tags` only, so the broker cannot serve as an open
    relay. Receive filtering stays open: `plc_tags` is the only publishable
    topic, so restricting receive adds nothing.
    """
    # ponytail: password file in %TEMP% per port; switch to a managed
    # location if multiple brokers per machine ever matter
    passwd_path = Path(tempfile.gettempdir()) / f"mqtt_passwd_{port}"
    passwd_path.write_text(
        f"{username}:{PasswordHash((Argon2Hasher(),)).hash(password)}\n",
        encoding="utf-8",
    )
    log.info(
        "Starting MQTT broker on 0.0.0.0:%s (shared credential, plc_tags only)", port
    )
    return Broker({
        "listeners": {"default": {"type": "tcp", "bind": f"0.0.0.0:{port}", "max_connections": 100}},
        "plugins": {
            "amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": False},
            "amqtt.plugins.authentication.FileAuthPlugin": {"password_file": str(passwd_path)},
            "amqtt.plugins.topic_checking.TopicAccessControlListPlugin": {
                "publish_acl": {username: ["plc_tags"]},
                "acl": {username: ["plc_tags"]},
            },
        },
    })
