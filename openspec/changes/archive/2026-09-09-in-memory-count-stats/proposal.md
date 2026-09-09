# Proposal: In-memory count statistics

## Why

Cycle-completion and metal-detection counts are the only reason the dashboard requires a configured PostgreSQL database (`DATABASE_URL`): both data sources write each event to a `line_events` table and `/api/stats` aggregates it. The OEE panel already takes its database connection at runtime from the user, so the configured DSN serves no other purpose. Owning the per-minute counting inside the dashboard process removes an operational dependency (a running PostgreSQL server) from every dashboard PC and simplifies setup.

## What Changes

- **BREAKING**: The dashboard no longer persists cycle/metal-detection events or counts to PostgreSQL. Per-minute counting is owned by the dashboard process in memory (a rolling 10-minute window of 1-minute buckets).
- Count history is process-local: restarting the dashboard resets the counts.
- Count data belongs to the *currently connected* PLC (direct or MQTT). Switching the data source (`/api/source`) or the MQTT line (`/api/line`) resets the counts for the new connection.
- **BREAKING**: `DATABASE_URL` is removed from the dashboard configuration (`app/config.py`, `.env.example`, tests). The dashboard requires no PostgreSQL DSN at startup; the OEE panel's runtime user-supplied connection is unchanged.
- Data sources (`PlcPoller`, `MqttLineSource`) stop writing events; they deliver edge events to the dashboard via a callback. The `dsn` parameter is removed from both sources and from `build_source`.
- `/api/stats` reads from the in-memory counter instead of SQL; its response shape is preserved (`{window_minutes, line_ip, points}`); the `line_ip` query parameter is ignored (counts only exist for the active connection).
- Removed from `app/db.py`: `line_events` schema, `ensure_schema`, `insert_event`, `per_minute_counts`. `scripts/init_db.py` no longer creates the dashboard database; it only ensures the OEE recorder database.
- Documentation updated (README, AGENTS.md); the documented limitation that edges missed while disconnected are unrecoverable is retained.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `production-statistics`: PostgreSQL persistence requirements (`Counter persistence in PostgreSQL`, `Line-scoped event persistence`) are replaced by in-process per-minute counting with process-lifetime and connection-switch reset semantics; the no-configured-database property is added; edge detection, no-phantom-count baseline, S3-independence, chart window, and the lost-edges limitation are retained.
- `plc-connectivity`: `Stats follow the active source` changes — after a source or line switch the per-minute charts start empty (counts reset) instead of showing the newly selected line's persisted counts.

## Impact

- `app/main.py` — in-memory counter wiring, `/api/stats`, `ensure_schema` call removed from lifespan.
- `app/plc.py`, `app/mqtt_source.py` — `insert_event` persistence replaced by an event callback; `dsn` parameter removed.
- `app/source_manager.py` — no longer passes `dsn`; reset hook for switches.
- new `app/stats.py` — per-minute counter (proposed in design).
- `app/config.py` — `database_url` field and `DATABASE_URL` requirement removed.
- `app/db.py`, `scripts/init_db.py` — dashboard/`line_events` portions removed.
- `.env.example`, README.md, AGENTS.md — configuration and docs.
- Tests: `test_db.py` (line_events parts) removed; `test_api.py`, `test_plc.py`, `test_mqtt_source.py`, `test_integration_mqtt.py`, `test_source_manager.py`, `test_config.py` updated; new counter tests. Some tests no longer require a PostgreSQL server.
- No PLC behaviour changes; PLC access remains read-only. OEE recorder and `oee` database are unaffected.
