"""MQTT wire protocol for the plc_tags topic: one fixed topic carrying a JSON
object that maps the 14 plc_tags.csv labels to booleans decoded from the snap7
process image. No timestamps, no line identity, no status messages."""

import json

from app.tags import TAGS

TAGS_TOPIC = "plc_tags"

# Label order follows the tag map derived from plc_tags.csv.
_LABELS = tuple(TAGS)


def encode_payload(raw: dict[str, bool]) -> str:
    """Encode a label->boolean map as the plc_tags JSON payload."""
    return json.dumps({label: bool(raw[label]) for label in _LABELS})


def parse_payload(payload: bytes | str) -> dict[str, bool]:
    """Decode and validate a plc_tags payload; raises ValueError when malformed.

    Strict: every label from plc_tags.csv must be present with a real boolean
    value. Unknown keys are ignored (forward compatibility)."""
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError(f"payload must be a JSON object, got {type(data).__name__}")
    values: dict[str, bool] = {}
    for label in _LABELS:
        value = data.get(label)
        if not isinstance(value, bool):
            raise ValueError(f"label '{label}' must be a boolean, got {value!r}")
        values[label] = value
    return values
