# Design: In-memory count statistics

## Context

Both data sources persist edge events themselves today: `PlcPoller._process` (app/plc.py:119-130) and `MqttLineSource._on_message` (app/mqtt_source.py:137-142) call `app.db.insert_event`, which opens a fresh psycopg connection per event to the `line_events` table. `/api/stats` (app/main.py:176-187) aggregates that table with `per_minute_counts` (SQL over a 10-minute `generate_series` window, filtered by `line_ip`). `DATABASE_URL` is a fail-fast required env var (app/config.py:93); after this change its only remaining consumers disappear, so it is removed entirely (user decision). The OEE panel already connects at runtime to a user-supplied DSN (fixed to database `oee`) and never touches `config.database_url`. Edge detection, the baseline-on-(re)connect invariant, and staleness handling live in the sources and stay untouched — the counter only ever sees events that already passed the baseline gate.

## Goals / Non-Goals

**Goals:**

- Dashboard-owned, thread-safe per-minute counter with the same response shape `/api/stats` has today.
- Count lifetime = process lifetime × current connection identity: reset on restart, source switch, and MQTT line switch.
- Remove the dashboard's configured PostgreSQL dependency completely (config, db helpers, init script, tests, docs).
- Preserve the no-phantom-count invariant across (re)connects, switches, and stale periods.

**Non-Goals:**

- No persistence or export of counts anywhere (no file, no DB, no MQTT).
- No per-line count history: switching lines shows an empty window; historical counts for other lines are out of scope.
- No changes to the OEE recorder, the `oee` database, or the OEE panel behaviour.
- No PLC-side changes; PLC access stays read-only.
- No change to `EVENT_EDGES` (P3 → cycle, B4 → metal) or edge/baseline logic.

## Decisions

**D1 — Event delivery: callback (`on_event`) passed into the sources.**
`PlcPoller` and `MqttLineSource` gain an `on_event: Callable[[str], None]` parameter (event type: `cycle_complete` | `metal_detected`); the `dsn` parameter is removed from both, from `build_source`, and from `SourceManager`'s config usage. main.py wires the counter's `record` method as the callback. Persistence call sites are replaced by the callback invocation, inside the same try/except so a counter error is logged and never kills the poller/MQTT thread.

- Alternative: events appended to the snapshot and drained by the UI poll — rejected: `/api/state` polling (browser, ~500 ms) is not aligned with the poller thread, so events could be missed or double-counted.
- Alternative: a `queue.Queue` that main drains in a consumer thread — functionally equivalent to the callback but adds a thread and lifecycle for no benefit at this event rate (≤ a few events/second).

**D2 — Counter: new `app/stats.py` with a `MinuteCounter` class.**
Owns a fixed-size ring of the last 10 wall-clock 1-minute buckets (plus the in-progress minute), each holding `{cycles, metal}` counters. Buckets are keyed by local wall-clock minute (`datetime.now()` truncated to the minute), matching today's `HH24:MI` labels, which came from the DB server clock on the same host. API:

- `record(event_type)` — bump the current minute's counter, rolling old buckets off the ring.
- `snapshot(window_minutes=10)` — returns `[{minute: "HH:MM", cycles, metal}]` for the trailing window, zero-filled for minutes with no events (replacing the SQL `generate_series`), oldest → newest.
- `reset()` — clears all buckets.
- One `threading.Lock` guards everything: `record` runs on the poller thread or paho callback thread, `snapshot`/`reset` on request-handler threads.

**D3 — Counter ownership and reset wiring in main.py.**
main.py constructs one `MinuteCounter` and passes a bound `on_event` into `SourceManager` (which forwards it to `build_source`). For resets, `SourceManager.switch()` and `MqttLineSource.set_line()` invoke an optional `on_connection_change` callback (also supplied by main.py) after the new source/line is accepted, and `set_line` is a no-op when the selected line is unchanged (guard in main or the source; a same-line reselect must not wipe counts). Restart reset needs no code — process memory dies with the process.

- Alternative: reset keyed by connection identity inside the counter (it observes `source`+`line_ip` from every event and self-resets on change) — rejected: events are sparse, so a stale-period line switch could be observed late or not at all; explicit hooks at the two real switch points are deterministic.

**D4 — `/api/stats` reads the counter; `line_ip` parameter ignored.**
Response keeps the existing shape `{window_minutes, line_ip, points}` for frontend compatibility, but `line_ip` is the active connection's IP and `points` come from `MinuteCounter.snapshot(10)`. The request's `line_ip` query parameter is accepted and ignored (spec: "Stats request for a non-active line"). The frontend needs no changes (its `selectedLine` already mirrors `state.line_ip`); the `?line_ip=` suffix in STATS_URL can be dropped for tidiness or left as harmless.

**D5 — Config: remove `DATABASE_URL` completely.**
Delete `Config.database_url`, the `_require("DATABASE_URL")` call, and the DSN from `.env.example`. `.env` files that still contain it are simply ignored (dotenv sets an unused env var — harmless). `load_recorder_config` is untouched (`OEE_DATABASE_URL` is separate and still required).

**D6 — Removals in db.py, init_db.py, and tests.**
`app/db.py` keeps only the OEE functions (`ensure_oee_schema`, `test_oee_connection`, `insert_oee_row`, `latest_oee_row`, `oee_history`); `SCHEMA_SQL`, `ensure_schema`, `insert_event`, `per_minute_counts`, and `MINUTE_COUNTS_SQL` are deleted. `scripts/init_db.py` drops the dashboard-database section (no longer calls `load_config` for a DSN) and only ensures the `oee` database. Tests: `tests/test_db.py` (line_events suite) is deleted; `test_api.py`, `test_plc.py`, `test_mqtt_source.py`, `test_integration_mqtt.py`, `test_source_manager.py`, and `test_config.py` are updated to the callback/counter model; new `tests/test_stats.py` covers bucketing, window rollover, zero-fill, thread-safety smoke, and reset. Files that become entirely unnecessary are removed rather than stubbed (user request).

**D7 — Docs: README.md and AGENTS.md updated.**
AGENTS.md's project-layout line for `db.py` (`line_events` table) and the `/api/stats` description change to the in-memory counter; README's data-flow diagram and endpoint description are updated. The MQTT lost-edges limitation text is retained (it now also covers counts during downtime, which was already true).

## Risks / Trade-offs

- [Counts are volatile: a dashboard crash or restart loses history] → Accepted explicitly by the user; OEE history (the durable record) is unaffected because the recorder is a separate process with its own database.
- [Two dashboards watching the same line now report different counts] → Accepted; counts are per-dashboard-process by design. Documented in README.
- [Clock jump (NTP/DST) could skew or collapse minute buckets] → Same exposure as the old SQL window (which used the DB clock on the same host); at worst a few counts land in the wrong minute bucket. No mitigation needed for a lab/training line.
- [Counter callback exceptions could disrupt event flow] → The callback is invoked inside the existing per-event try/except in both sources; errors are logged, polling continues.
- [Stale-period events were already unrecoverable] → Unchanged; the baseline gate still prevents phantom counts across gaps, and the spec's lost-edges requirement remains.

## Migration Plan

1. Land the code change; run `scripts/init_db.py` once if the `oee` database does not yet exist (it no longer touches the dashboard database).
2. Remove `DATABASE_URL` from the PC's `.env` (or leave it — it is ignored); no data migration is needed or possible for `line_events` (the table is simply abandoned; dropping it is optional housekeeping).
3. Rollback = revert the commit and restore `DATABASE_URL` in `.env`; the old code resumes reading whatever is in `line_events`.

## Open Questions

None.
