import json

import pytest

from app.mqtt_proto import TAGS_TOPIC, encode_payload, parse_payload
from app.tags import TAGS

LABELS = list(TAGS)


def full_payload(**overrides):
    values = {label: False for label in LABELS}
    values.update(overrides)
    return values


def test_topic_is_fixed():
    assert TAGS_TOPIC == "plc_tags"


def test_encode_payload_has_all_labels_as_booleans():
    payload = json.loads(encode_payload(full_payload(ESO=True, B4=True)))
    assert set(payload.keys()) == set(LABELS)
    assert payload["ESO"] is True and payload["B4"] is True
    assert all(isinstance(v, bool) for v in payload.values())


def test_round_trip_decode():
    raw = full_payload(P3=True, S1=True)
    assert parse_payload(encode_payload(raw)) == raw


def test_non_boolean_labels_are_coerced_to_bool_on_encode():
    payload = json.loads(encode_payload(full_payload(B3=1)))
    assert payload["B3"] is True


def test_missing_label_rejected():
    data = json.loads(encode_payload(full_payload()))
    del data["B4"]  # unknown/missing label: strict payload requires all 14
    with pytest.raises(ValueError):
        parse_payload(json.dumps(data))


@pytest.mark.parametrize("bad", [0, 1, "true", None, [True]])
def test_non_boolean_value_rejected(bad):
    data = full_payload()
    data["S1"] = bad
    with pytest.raises(ValueError):
        parse_payload(json.dumps(data))


def test_unknown_keys_ignored():
    data = full_payload()
    data["EXTRA"] = "whatever"
    data["ts"] = "2026-09-09T00:00:00Z"
    assert parse_payload(json.dumps(data)) == full_payload()


@pytest.mark.parametrize("payload", [b"not json", b"[]", b"42", b"null", ""])
def test_malformed_payloads_rejected(payload):
    with pytest.raises(ValueError):
        parse_payload(payload)
