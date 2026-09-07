## Context

The dashboard today is a single-process FastAPI app with a background `PlcPoller` thread that reads one S7-1200 via snap7 (~500 ms), detects P3/B4 rising edges, and persists events to local PostgreSQL (`app/plc.py`, `app/edges.py`, `app/db.py`). Tag semantics (addresses, active-low S1/ESO) live in `app/tags.py` from `plc_tags.csv`. Config is fail-fast env vars in `.env` (`app/config.py`). Existing specs: `line-state-monitoring`, `plc-connectivity`, `production-statistics`.

The change splits the architecture into per-line publisher PCs (broker + publisher) and a central dashboard that subscribes to the selected line. Decisions below were validated during requirements analysis (see proposal.md for the closed gap matrix).

## Goals / Non-Goals

**Goals:**
- Raw process image (I/Q bytes) published over MQTT per line; dashboard decodes with existing `tags.py` so tag semantics have exactly one owner.
- Dashboard can run in `direct` mode (current behaviour, untouched) or `mqtt` mode with runtime line switching.
- Clear liveness: LWT + retained messages + age-based staleness; edge re-baseline on connect/switch/stale preserves the no-phantom-count invariant.
- Tests still run with no PLC; MQTT tests use fakes/in-process broker.

**Non-Goals:**
- Concurrent display of multiple lines (one line at a time).
- MQTT TLS, authentication, MQTT 5 features, cloud brokers, discovery protocols.
- Central collection of all lines' data simultaneously; only the selected line's events are persisted.
- Writing to the PLC (forever out of scope).

## Decisions

- **D1 — Publisher library & broker: amqtt; subscriber: paho-mqtt.** amqtt is pure Python, installs in the venv (user requirement), supports MQTT 3.1.1 retained + LWT + anonymous clients, and can be launched programmatically (enables an in-process integration test). paho-mqtt is the de-facto sync client; the dashboard is threaded (not asyncio), so a callback-driven sync client fits the existing `PlcPoller`-style design. Alternative considered: Mosquitto binary — rejected (user wants pip-only). Alternative for subscriber: amqtt client — rejected (asyncio-only; forces an event-loop bridge for marginal gain).
- **D2 — Payload: hex-encoded raw I/Q bytes.** `inputs_hex`/`outputs_hex` (2 bytes each) + `plc_ip` + publisher UTC ISO `ts`. The publisher stays generic; `tags.py` remains the single source of tag truth on the dashboard. Alternative (named bool dict) rejected: would embed the tag map in the publisher and duplicate polarity logic.
- **D3 — Topics: `plc/<line-ip>/state` (retained snapshot) and `plc/<line-ip>/status` (retained `online`/`offline` LWT).** Line IP is the PLC's address, matching the user story's "identified by IP". Retained state + status give instant snapshots on subscribe; LWT distinguishes publisher death from broker death (broker itself dying is covered by snapshot-silence staleness).
- **D4 — Edge detection stays on the dashboard, in MQTT mode.** The MQTT source feeds decoded snapshots into the existing `detect_events`; first message after connect/switch/stale is baseline-only. Events persist to the dashboard's central Postgres, so `/api/stats` needs no per-line HTTP proxying. Accepted trade-off: edges occurring while the dashboard is stale/switched-away are lost (documented in the production-statistics delta). Alternative (count on line PCs, dashboard fetches) rejected as out of proportion for this course project.
- **D5 — Source abstraction.** Extract the snapshot contract (`snapshot()` shape: `connected`, `stale`, `last_update`, `values`, plus new `line_ip`, `source`) into a common shape implemented by `PlcPoller` (direct, extended minimally) and a new `MqttLineSource` (paho client in a thread; retained-state tracking; staleness timer ~2 s = 4 poll intervals; `set_line()` to switch: unsubscribe, clear snapshot, re-baseline). `main.py` wires one source by `DATA_SOURCE`; the API exposes the line list and accepts a line-selection change.
- **D6 — Line registry in env.** `LINES="192.168.0.1=192.168.0.11:1883,192.168.0.2=192.168.0.12:1883"` parsed by `config.py`; `MQTT_BROKER_HOST`/`MQTT_BROKER_PORT` define the default/selected line. Registry parsed fail-fast like existing config. Alternative (JSON file, runtime discovery) rejected: YAGNI for a fixed lab network.
- **D7 — DB migration: additive.** `line_events` gains a `line_ip TEXT NOT NULL` column; `scripts/init_db.py` alters the table if it exists (or the table is recreated in dev) and existing rows are backfilled with the configured `PLC_IP`. All event queries filter by `line_ip`.
- **D8 — Separate entrypoints on the line PC.** `scripts/run_broker.py` (starts amqtt on `BROKER_PORT`) and `app/publisher.py` (snap7 read loop → publish). Separate processes: a publisher crash leaves the broker up and the LWT fires correctly; the broker can serve multiple publishers if the topology grows.

## Risks / Trade-offs

- [Edges lost while stale/switched] → Accepted and documented in UI/docs; re-baseline prevents phantom counts from masking the gap.
- [amqtt is asyncio-based; embedding in tests/entrypoint must manage the event loop] → Isolate inside the broker entrypoint and the optional integration test only; no asyncio in the dashboard path.
- [Plain MQTT, no auth/TLS] → Accepted per user for this lab network; brokers must not be exposed beyond the lab segment.
- [Clock skew between line PC and dashboard] → Snapshot `ts` is informational (displayed "last update"); staleness uses the dashboard's own receive clock, not publisher timestamps.
- [Line switch while a stale timer is pending] → `set_line()` cancels timers and clears state atomically under the source's lock before reconnecting.
- [paho-mqtt network loop thread dying silently] → Loop-start with reconnect-on-failure settings; staleness timer is the backstop either way.
