## Why

The dashboard monitors exactly one PLC line, hard-wired to a single direct S7 connection. To supervise several conveyor lines from one dashboard, the raw process image of each PLC must be published over MQTT from a PC next to the line, and the dashboard must be able to pick — at runtime — which line it subscribes to.

## What Changes

- Add a **line-PC publisher** (separate entrypoint) that reads the S7-1200 process image read-only and publishes the raw inputs/outputs bytes as a retained JSON snapshot to a per-line MQTT topic at the poll interval.
- Add a **local MQTT broker entrypoint** (amqtt, pure Python, installed in the project venv) to run on each line PC; plain MQTT, no password, no TLS.
- Add **MQTT liveness semantics**: Last Will and Testament status topic (`online`/`offline`, retained), retained snapshots, and dashboard-side age-based staleness (~2 s silence ⇒ stale).
- Add a **dashboard MQTT data source**: `DATA_SOURCE=direct` (existing snap7 path, behaviour unchanged) or `DATA_SOURCE=mqtt` (subscribe to the selected line's broker).
- Add a **line registry** (`LINES` = `PLC_IP=host:port,...`) and a **line dropdown** in the UI; one line selected at a time; switching clears the snapshot, shows "connecting…", then live/stale.
- In MQTT mode, **edge detection and event persistence move to the dashboard side**: the subscriber decodes the raw bytes with the existing tag map, detects P3/B4 rising edges with a re-baseline on connect/switch/stale, and persists events to the central PostgreSQL — edges occurring while a broker is down are lost (accepted, documented).
- Events become **line-scoped** (`line_ip` column) so per-minute statistics follow the selected line; `/api/stats` gains a line filter.
- Payload carries the **raw I/Q bytes as hex** (`inputs_hex`/`outputs_hex` + publisher UTC timestamp + `plc_ip`); the dashboard remains the single source of truth for tag semantics (`plc_tags.csv`, polarity).

## Capabilities

### New Capabilities

- `mqtt-line-transport`: Publishing the raw PLC process image over MQTT from a line PC — broker lifecycle, per-line topics and payload, retained snapshots, Last Will & Testament, publish cadence, and the subscriber protocol contract the dashboard relies on.

### Modified Capabilities

- `plc-connectivity`: The dashboard gains a selectable data source (direct S7 vs. MQTT), a registry of lines (`PLC_IP → broker host:port`), runtime line switching with connecting/stale states, and MQTT-based liveness (LWT + message-age staleness) in addition to the existing direct-connection staleness.
- `production-statistics`: Cycle/metal events are recorded per line (`line_ip`), the dashboard-side subscriber performs edge detection in MQTT mode with re-baseline on connect/switch, and per-minute charts are scoped to the selected line.

## Impact

- **New code**: `app/publisher.py`, `app/broker.py` (or `scripts/run_broker.py`), `app/mqtt_source.py` (dashboard subscriber), shared payload/topic module (`app/mqtt_proto.py`).
- **Modified code**: `app/config.py` (new env vars), `app/main.py` (wire data source, line selection endpoint), `app/db.py` (`line_events` gains `line_ip`), `app/plc.py` (poller reports `line_ip`; direct path otherwise unchanged), `app/static/index.html` (line dropdown, source badge, connecting/offline states), `.env.example`.
- **Dependencies**: `amqtt` (broker + publisher client), `paho-mqtt` (dashboard subscriber) added to `requirements.txt` and installed in the venv.
- **Database**: schema change on `line_events` (add `line_ip`, backfill existing rows with the configured `PLC_IP`); `scripts/init_db.py` updated.
- **Testing**: new tests use a fake/in-process MQTT client (no PLC, no external broker needed); optional in-process amqtt round-trip test. Existing tests keep the "no PLC needed" guarantee.
- **Unchanged**: PLC access stays strictly read-only (PUT/GET); no PLC writes anywhere in the new components.
