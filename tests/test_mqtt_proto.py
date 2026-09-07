import json

import pytest

from app.mqtt_proto import (
    encode_snapshot,
    parse_snapshot,
    state_topic,
    status_topic,
)


def test_topic_helpers():
    assert state_topic("192.168.0.1") == "plc/192.168.0.1/state"
    assert status_topic("192.168.0.1") == "plc/192.168.0.1/status"


def test_encode_snapshot_payload_shape():
    payload = json.loads(
        encode_snapshot("10.0.0.5", bytes([0b1010_0000, 0x01]), bytes([0x00, 0xFF]))
    )
    assert set(payload.keys()) == {"plc_ip", "ts", "inputs_hex", "outputs_hex"}
    assert payload["plc_ip"] == "10.0.0.5"
    assert payload["inputs_hex"] == "a001"
    assert payload["outputs_hex"] == "00ff"


def test_round_trip_decode():
    inputs, outputs = bytes([0b1010_0000, 0x01]), bytes([0x00, 0xFF])
    data = parse_snapshot(encode_snapshot("10.0.0.5", inputs, outputs))
    assert data["inputs"] == inputs
    assert data["outputs"] == outputs
    assert data["plc_ip"] == "10.0.0.5"
    assert data["ts"]  # ISO-8601 string present


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"[]",
        b'{"plc_ip": "x", "ts": "t", "inputs_hex": "0000"}',  # missing key
        b'{"plc_ip": "", "ts": "t", "inputs_hex": "0000", "outputs_hex": "0000"}',
        b'{"plc_ip": "x", "ts": 5, "inputs_hex": "0000", "outputs_hex": "0000"}',
        b'{"plc_ip": "x", "ts": "t", "inputs_hex": "zzzz", "outputs_hex": "0000"}',
        b'{"plc_ip": "x", "ts": "t", "inputs_hex": "0000", "outputs_hex": "000"}',  # 1 byte
        b'{"plc_ip": "x", "ts": "t", "inputs_hex": "000000", "outputs_hex": "0000"}',  # 3 bytes
    ],
)
def test_malformed_payloads_rejected(payload):
    with pytest.raises(ValueError):
        parse_snapshot(payload)
