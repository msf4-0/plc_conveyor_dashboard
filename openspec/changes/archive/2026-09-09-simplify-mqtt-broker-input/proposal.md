# Proposal: simplify-mqtt-broker-input

## Why

Pointing the dashboard at a line's MQTT broker currently requires pre-registering
every line in `.env` (`LINES`, `MQTT_BROKER_HOST/PORT`) and picking from a
dropdown, and the wire protocol (hex-encoded raw I/Q bytes, per-line topics,
`online/offline` status + LWT) is heavier than this course project needs. Letting
the user simply type a broker IP, and reducing the protocol to one topic of
label-keyed booleans judged alive on packet cadence alone, makes MQTT mode
self-service and the code much smaller.

## What Changes

- **BREAKING** MQTT wire protocol: one fixed topic `plc_tags`, payload is a JSON
  object with exactly the 14 labels from `plc_tags.csv` (`ESO, S1, S2, S3, B1,
  B2, B3, B4, K1, K2, K3, P1, P2, P3`) mapped to booleans decoded from the snap7
  process image; unknown keys are ignored.
- **BREAKING** No retain flag, no status topic, no Last Will: liveness is judged
  by the dashboard as "stale when no packet has arrived for ~1 second"
  (previously ~2 s silence or an `offline` status message). No snapshot is
  credited across a silence gap (re-baseline invariant kept).
- **BREAKING** `app/publisher.py` publishes the new `plc_tags` payload; the
  amqtt broker (`app/broker.py`, `scripts/run_broker.py`) is unchanged.
- **BREAKING** Dashboard MQTT target is a user-typed broker address
  (`IP` or `IP:port`, bare IP defaults to port 1883) entered in the UI instead of
  the line dropdown; it is remembered in browser localStorage (like the OEE
  connection bar) and auto-reconnected on page load.
- The `LINES` registry, `MQTT_BROKER_HOST/PORT` environment variables, the
  `/api/line` endpoint, and the line dropdown are removed. `DATA_SOURCE` still
  selects the startup source; MQTT mode starts in "connecting" until an IP is
  submitted.
- Switching the MQTT broker at runtime rebuilds the MQTT source with the same
  cleared-values / connecting / re-baseline semantics as a source switch.
- Per-minute statistics follow the active connection, now identified by the
  typed broker endpoint in MQTT mode; a broker change resets the counters.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `mqtt-line-transport`: payload format, topic layout, retain, and LWT
  requirements are replaced by the single-topic `plc_tags` boolean payload; the
  publisher no longer publishes any status.
- `plc-connectivity`: MQTT mode selects its broker by a user-typed address
  instead of the line registry/dropdown; liveness becomes silence-based
  (~1 s); stats follow the typed broker endpoint; the line-registry and
  line-switching requirements are removed.
- `production-statistics`: per-minute counts are keyed to the active connection,
  identified in MQTT mode by the typed broker endpoint; a broker change resets
  the counters.

## Impact

- **Code:** `app/mqtt_proto.py` (rewritten around `plc_tags`), `app/mqtt_source.py`
  (single topic, strict payload, 1 s silence staleness, no status handling, no
  lines registry), `app/publisher.py` (new payload, no retain/LWT),
  `app/config.py` (drop `MQTT_BROKER_*`, `LINES`), `app/source_manager.py`
  (broker-address-based MQTT source building/switching), `app/main.py`
  (drop `/api/line`, accept broker address on source selection),
  `app/static/index.html` (text input + connect in place of the dropdown,
  localStorage pre-fill/auto-connect).
- **Config/docs:** `.env.example`, `README.md`, `AGENTS.md` layout notes.
- **Tests:** `tests/test_mqtt_source.py`, `tests/test_integration_mqtt.py`,
  `tests/test_config.py`, `tests/test_api.py`, `tests/test_source_manager.py`,
  publisher tests, and any tag/codec tests touching `mqtt_proto`.
- **Deployment:** publisher and dashboard must be updated together per line
  (protocol is not backward compatible). Direct mode is untouched.
- **Depends on:** `in-memory-count-stats` is applied first — both changes touch
  `app/mqtt_source.py`, `app/main.py`, and the same tests.
