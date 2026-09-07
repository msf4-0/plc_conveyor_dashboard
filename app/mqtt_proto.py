import binascii
import json
from datetime import datetime, timezone

PAYLOAD_KEYS = {"plc_ip", "ts", "inputs_hex", "outputs_hex"}


def state_topic(line_ip: str) -> str:
    return f"plc/{line_ip}/state"


def status_topic(line_ip: str) -> str:
    return f"plc/{line_ip}/status"


def encode_snapshot(line_ip: str, inputs: bytes | bytearray, outputs: bytes | bytearray) -> str:
    return json.dumps(
        {
            "plc_ip": line_ip,
            "ts": datetime.now(timezone.utc).isoformat(),
            "inputs_hex": bytes(inputs).hex(),
            "outputs_hex": bytes(outputs).hex(),
        }
    )


def parse_snapshot(payload: bytes | str) -> dict:
    """Decode and validate a snapshot payload; raises ValueError when malformed."""
    data = json.loads(payload)
    if not isinstance(data, dict) or set(data) != PAYLOAD_KEYS:
        raise ValueError(f"unexpected payload keys: {sorted(data) if isinstance(data, dict) else type(data)}")
    if not isinstance(data["plc_ip"], str) or not data["plc_ip"]:
        raise ValueError("plc_ip must be a non-empty string")
    if not isinstance(data["ts"], str):
        raise ValueError("ts must be an ISO-8601 string")
    for key in ("inputs_hex", "outputs_hex"):
        if not isinstance(data[key], str):
            raise ValueError(f"{key} must be a hex string")
        try:
            raw = binascii.unhexlify(data[key])
        except (binascii.Error, ValueError):
            raise ValueError(f"{key} is not valid hex") from None
        if len(raw) != 2:
            raise ValueError(f"{key} must encode exactly 2 bytes, got {len(raw)}")
    data["inputs"] = binascii.unhexlify(data["inputs_hex"])
    data["outputs"] = binascii.unhexlify(data["outputs_hex"])
    return data
