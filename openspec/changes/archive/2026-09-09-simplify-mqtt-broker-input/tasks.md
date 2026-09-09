# Tasks: simplify-mqtt-broker-input

## 1. Protocol module

- [x] 1.1 Rewrite `app/mqtt_proto.py`: `TAGS_TOPIC = "plc_tags"`, `encode_payload(raw: dict[str, bool]) -> str` and `parse_payload(payload) -> dict[str, bool]` (exactly the 14 `plc_tags.csv` labels, strict booleans, unknown keys ignored, `ValueError` otherwise); delete `state_topic`/`status_topic`/`encode_snapshot`/`parse_snapshot`. Verify: new unit tests in `tests/test_mqtt_proto.py` for round-trip, strict-label rejection, non-boolean rejection, unknown-key tolerance; `.\.venv\Scripts\python.exe -m pytest tests/test_mqtt_proto.py -q` passes.

## 2. Publisher

- [x] 2.1 Update `app/publisher.py`: publish `encode_payload(raw_values(inputs, outputs))` to `TAGS_TOPIC` with `qos=0` and no retain; remove `will_set`, the connect-time `online` publish, and the shutdown `offline` publish. Verify: `pytest tests/ -q -k publisher` (or the publisher test file) passes with the fake reader.

## 3. MQTT source (dashboard)

- [x] 3.1 Rewrite `app/mqtt_source.py`: `MqttLineSource(broker_host, broker_port, poll_interval_ms, on_event, staleness_ms=1000, client_factory=make_paho_client)`; subscribe to `plc_tags` only; parse with `parse_payload` and feed values straight to `build_view`; delete `_status_online`, `set_line`, the `lines` registry, and `line_ip`; report `broker = "host:port"` in `snapshot()`. Verify: updated `pytest tests/test_mqtt_source.py -q` covers stale-at-1 s silence, no status topic, re-baseline after silence gap, and event callback invocation.
- [x] 3.2 Update the stale-resume path: first packet after a stale period sets `_baseline = True` and produces no events. Verify: a `test_mqtt_source.py` case asserting zero events across the gap and counting resumes on the next rising edge.

## 4. Config

- [x] 4.1 Remove `mqtt_broker_host`, `mqtt_broker_port`, `lines`, `_parse_lines`, and the MQTT block from `load_config()` in `app/config.py`; keep `DATA_SOURCE` validation and `BROKER_HOST/BROKER_PORT`. Update `.env.example` accordingly (drop MQTT_BROKER_*, LINES). Verify: `pytest tests/test_config.py -q` passes after removing registry/broker cases; dashboard config loads from a minimal `.env` with no DB/MQTT vars.

## 5. Source manager + API

- [x] 5.1 Update `app/source_manager.py`: `build_source(config, name, broker=None)` builds `MqttLineSource` from `(host, port)` with no lines; `SourceManager` supports an inactive MQTT slot at startup (snapshot shows `connecting`, `broker: null`) and rebuilds the source when `switch()` is called for the active source with a different broker. Verify: `pytest tests/test_source_manager.py -q` passes for direct, mqtt-with-broker, and rebuild-on-new-broker cases.
- [x] 5.2 Update `app/main.py`: parse `broker` (`"IP"` or `"IP:port"`, default port 1883, 400 on malformed/out-of-range port) on `POST /api/source {source: "mqtt", broker}`; delete `POST /api/line`; `/api/state` and `/api/stats` key the connection by the broker string. Verify: `pytest tests/test_api.py -q` passes including new broker-parse error cases and 400 when switching to MQTT without a broker.

## 6. Frontend

- [x] 6.1 Update `app/static/index.html`: replace `#line-select`/`#line-label` with `#mqtt-broker` text input + Connect button (visible in MQTT mode only, Enter submits); POST `/api/source` with the typed broker; remove dropdown population logic and the local `selectedLine` stats keying (use the backend-reported active connection). Verify: manual browser check against a test broker — typed IP connects, `IP:port` honoured, retyping an address clears values and re-connects.
- [x] 6.2 Add localStorage persistence: store the submitted broker string on successful submit, pre-fill and auto-connect on page load (mirroring the OEE connection bar pattern). Verify: browser test — reload after connecting auto-reconnects; stale/connecting banner behaves per spec.

## 7. Integration, docs, validation

- [x] 7.1 Update `tests/test_integration_mqtt.py`: in-process broker publishes a `plc_tags` payload (no retain/status); dashboard source delivers values and counts one P3/B4 edge. Verify: `pytest tests/test_integration_mqtt.py -q` passes.
- [x] 7.2 Update `README.md` (architecture diagram, MQTT mode setup, env vars) and AGENTS.md project-layout notes (mqtt_proto/publisher/mqtt_source/config/main descriptions, no LINES registry). Verify: README setup steps match `.env.example`; no remaining references to `LINES`, `MQTT_BROKER_*`, `/api/line`, or the status topic.
- [x] 7.3 Full test suite: `.\.venv\Scripts\python.exe -m pytest tests -q` passes.
- [x] 7.4 End-to-end smoke: run `scripts/run_broker.py` + `python -m app.publisher` against a simulated/fake PLC, run the dashboard, connect via the typed IP, confirm values render, staleness appears ~1 s after stopping the publisher, and per-minute charts reset when a new broker is submitted. Verify: observed in a browser.
