# Tasks: In-memory count statistics

## 1. Counter module

- [x] 1.1 Create `app/stats.py` with `MinuteCounter` (`record`, `snapshot(window_minutes=10)`, `reset`), a 10-bucket rolling wall-clock minute ring, zero-filled `HH:MM` labels, and a `threading.Lock`; verify with new `tests/test_stats.py` covering record/label, window rollover, zero-fill ordering, `reset`, and a concurrent record/snapshot smoke test; run `pytest tests/test_stats.py -q`.

## 2. Sources deliver events via callback

- [x] 2.1 In `app/plc.py`: add `on_event: Callable[[str], None] | None = None` to `PlcPoller.__init__`, remove `dsn` and the `app.db.insert_event` import, and in `_process` call the callback per detected event inside the existing try/except; verify `pytest tests/test_plc.py -q` (updated in 2.3).
- [x] 2.2 In `app/mqtt_source.py`: same change for `MqttLineSource` (`dsn` removed, callback invoked per event in `_on_message`'s event loop); verify `pytest tests/test_mqtt_source.py -q` (updated in 2.3).
- [x] 2.3 Update `tests/test_plc.py` and `tests/test_mqtt_source.py`: replace DB assertions with callback-capture fakes (event type + no-DB requirement), and update `tests/test_source_manager.py` + `tests/test_integration_mqtt.py` to construct sources/config without `dsn`; verify `pytest tests/test_plc.py tests/test_mqtt_source.py tests/test_source_manager.py tests/test_integration_mqtt.py -q`.

## 3. Reset hooks on connection change

- [x] 3.1 In `app/source_manager.py`: thread `on_event` through `build_source`/`SourceManager`, remove `dsn=config.database_url` usage, and invoke an optional `on_connection_change` callback after a successful `switch()` (and from `set_line` when the line actually changes); verify `pytest tests/test_source_manager.py -q`.
- [x] 3.2 Add source-manager/counter reset tests: switch resets the counter, same-line reselect does not; verify with the updated test suite.

## 4. Dashboard API and lifespan

- [x] 4.1 In `app/main.py`: instantiate `MinuteCounter`, wire `on_event`/`on_connection_change` into `SourceManager`, drop the `ensure_schema` call from `lifespan`, and rewrite `/api/stats` to return `{window_minutes: 10, line_ip: <active>, points: counter.snapshot(10)}` ignoring the `line_ip` query param; verify `pytest tests/test_api.py -q`.
- [x] 4.2 Update `tests/test_api.py`: `/api/stats` against a fake/seeded counter (no PostgreSQL), including the ignored `line_ip` param and post-switch empty window; verify `pytest tests/test_api.py -q`.

## 5. Remove the configured database dependency

- [x] 5.1 In `app/config.py`: delete `Config.database_url` and `_require("DATABASE_URL")`; update `.env.example` (remove `DATABASE_URL`); verify `pytest tests/test_config.py -q` after updating its env fixtures.
- [x] 5.2 In `app/db.py`: delete `SCHEMA_SQL`, `MINUTE_COUNTS_SQL`, `ensure_schema`, `insert_event`, `per_minute_counts` (OEE functions stay); delete `tests/test_db.py`; verify `python -c "import app.db"` and `pytest tests/test_db_oee.py -q`.
- [x] 5.3 In `scripts/init_db.py`: remove the dashboard-database section (keep only the `oee` database creation + `ensure_oee_schema`); verify by running `.\.venv\Scripts\python.exe scripts\init_db.py` against the dev DB (oee schema ensured, no `line_events` access).

## 6. Frontend and docs

- [x] 6.1 `app/static/index.html`: drop the `?line_ip=` suffix from STATS_URL if present (response shape unchanged); verify manually that charts render from `/api/stats`.
- [x] 6.2 Update README.md and AGENTS.md: data-flow diagram (in-memory counter, no dashboard DB), `/api/stats` description, `app/db.py` layout line, and the retained lost-edges limitation plus the "counts are per-dashboard-process and reset on restart/switch" note.

## 7. Verification

- [x] 7.1 Full suite without any PostgreSQL dependency: temporarily stop/rename the dev DB DSN assumption by running `pytest tests -q` (suite must pass with no reachable database except tests that explicitly use one — only the OEE DB tests remain, which may still require the local `oee` DB).
- [x] 7.2 End-to-end smoke: start the dashboard (`python -m uvicorn app.main:app`) with `DATABASE_URL` removed from `.env`, confirm it serves the UI, `/api/stats` returns zero-filled points, a source switch (or line switch) resets the charts, and restart resets counts; verify with a browser against a simulated PLC/MQTT publisher. (Verified by the user in the browser; server started cleanly with `DATABASE_URL` absent.)
