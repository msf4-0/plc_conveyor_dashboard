## 1. Dependencies & shared protocol

- [x] 1.1 Add `amqtt` and `paho-mqtt` to `requirements.txt` and install with `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`; verify both import in the venv (`python -c "import amqtt, paho.mqtt"`).
- [x] 1.2 Create `app/mqtt_proto.py` with topic helpers (`state_topic(ip)`, `status_topic(ip)`) and payload codec (`encode_snapshot`, `parse_snapshot`) for `{plc_ip, ts, inputs_hex, outputs_hex}`; verify with unit tests covering round-trip encode/decode and rejection of malformed payloads (`tests/test_mqtt_proto.py`).

## 2. Config & database

- [x] 2.1 Extend `app/config.py`: `DATA_SOURCE` (`direct`|`mqtt`), `MQTT_BROKER_HOST`/`MQTT_BROKER_PORT`, optional `BROKER_PORT`, `LINES` registry parser (`PLC_IP=host:port,...`); fail-fast on invalid values and make MQTT vars required only when `DATA_SOURCE=mqtt`; verify with config unit tests for valid/invalid/missing cases.
- [x] 2.2 Add `line_ip TEXT NOT NULL` to the `line_events` schema in `app/db.py` and update `insert_event` to accept it; backfill/alter logic + updated `scripts/init_db.py`; verify by running `scripts\init_db.py` against the dev DB and inserting a row.
- [x] 2.3 Update `per_minute_counts` to filter by `line_ip` and update existing `db` tests accordingly; verify with `pytest tests -q`.

## 3. Line-PC broker & publisher

- [x] 3.1 Create `scripts/run_broker.py` launching amqtt on `BROKER_PORT` (no auth), with connection/disconnection logging; verify by starting it and connecting with a throwaway paho client subscribe/publish round-trip.
- [x] 3.2 Create `app/publisher.py` (entrypoint `python -m app.publisher` or script): reuses `Snap7Reader` read-only, publishes retained snapshot to `plc/<ip>/state` each poll interval, registers retained `offline` LWT on `plc/<ip>/status`, publishes retained `online` after connect and `offline` on clean shutdown; verify with a fake reader + in-process broker test asserting cadence, retain flags, and LWT message.
- [x] 3.3 Document line-PC setup (broker + publisher, `.env` keys) in the README section added in task 5.3.

## 4. Dashboard MQTT source & API

- [x] 4.1 Create `app/mqtt_source.py` (`MqttLineSource`): paho-mqtt client in a background thread; subscribes to the selected line's `state`/`status` topics; decodes payloads with `tags.raw_values`; exposes the same `snapshot()` shape as `PlcPoller` plus `line_ip` and `source`; staleness when status is `offline` or no snapshot for ~2 s; `set_line()` unsubscribes, clears snapshot, re-baselines; edge detection via `detect_events` (baseline-only on first/switch/stale resume) and persistence via `insert_event` with `line_ip`; verify with unit tests using a fake paho client: connect/retained snapshot, staleness timer, LWT offline, switch re-baseline, edge counting.
- [x] 4.2 Extend `app/plc.py` (`PlcPoller.snapshot()`) and `main.py` wiring: instantiate `PlcPoller` (direct) or `MqttLineSource` (mqtt) by `DATA_SOURCE`; pass `line_ip` in both; `/api/state` includes `line_ip`, `source`, and the line list; new `POST /api/line` (or equivalent) to switch lines in mqtt mode; verify with existing FastAPI/httpx tests extended for both modes (fake source injection).
- [x] 4.3 Update `.env.example` with the new direct/MQTT blocks and `LINES` registry examples; verify a fresh copy + fill-in boots the server in both `DATA_SOURCE` modes (mqtt pointing at a locally started broker).

## 5. UI, docs & final verification

- [x] 5.1 Update `app/static/index.html`: line dropdown (mqtt mode only), source badge (direct/MQTT), "connecting…" and stale/offline states, line-scoped stats polling (`/api/stats?line_ip=`); verify manually in a browser against an in-process broker + publisher with a simulated line.
- [x] 5.2 Add integration test: in-process amqtt broker + publisher (fake reader) + `MqttLineSource` end-to-end — retained snapshot received, edges counted after baseline, LWT offline on publisher crash; mark so it runs in default `pytest tests -q` without a PLC.
- [x] 5.3 Update README: architecture diagram (line PC broker+publisher, dashboard subscriber), setup for each line PC, dashboard env vars, and the "edges lost while stale/disconnected" limitation; verify docs match the delivered env keys and entrypoints.
- [x] 5.4 Full verification: `.\.venv\Scripts\python.exe -m pytest tests -q` green; boot server in `direct` mode and confirm behaviour unchanged; boot broker+publisher+dashboard in `mqtt` mode, switch lines in the UI, and confirm stale/recovery/switch behaviour per specs.
