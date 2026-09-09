## 1. Configuration and database groundwork

- [x] 1.1 Add recorder env vars (`OEE_DATABASE_URL`, `OEE_WRITE_INTERVAL_S` default 1, `IDEAL_CYCLE_TIME_S` default 5) to `.env.example` with comments, and add `load_recorder_config()` to `app/config.py` with fail-fast validation (write interval > 0, ideal CT 0.1–3600, no dashboard vars required); verify with new cases in `tests/test_config.py` (`pytest tests/test_config.py -q`).
- [x] 1.2 Add OEE database access to `app/db.py`: `ensure_oee_schema` (create table `oee` if absent) and `insert_oee_row`; verify via `tests/test_db_oee.py` against the test database (`pytest tests/test_db_oee.py -q`).
- [x] 1.3 Extend `scripts/init_db.py` to create the `oee` database (connecting via the maintenance `postgres` database) when missing; verify by dropping `oee` locally, running the script, and confirming the database exists.

## 2. Simplified OEE engine and recorder

- [x] 2.1 Rewrite `app/oee.py` as the simplified engine: ungated B3/B1 cycle counting with B2/B4 latches and in-flight-as-bad, run time while connected, stop time while P1 on, disconnect pause + edge re-baseline, A/P/Q/OEE computation with NULL (None) when run time is zero; remove state machine, reset, and ideal-CT setter; verify with rewritten `tests/test_oee_counts.py`, `tests/test_oee_time.py`, `tests/test_oee_metrics.py` (`pytest tests/test_oee_counts.py tests/test_oee_time.py tests/test_oee_metrics.py -q`).
- [x] 2.2 Create `app/recorder.py` (`python -m app.recorder`): own `Snap7Reader` poll loop feeding the engine, insert row every `OEE_WRITE_INTERVAL_S` with UTC wall-clock timestamp, log-and-continue on DB failure, pause/re-baseline on PLC failure; verify with a recorder-loop test using a fake reader/DB in `tests/test_recorder.py` (`pytest tests/test_recorder.py -q`).
- [x] 2.3 Delete `tests/test_oee_state.py` (state machine tests are obsolete); verify `pytest tests -q` reports no import errors.

## 3. Dashboard backend

- [x] 3.1 Remove `oee_engine` plumbing from `app/plc.py`, `app/mqtt_source.py`, `app/source_manager.py`, and drop `line_state`/`oee_paused` from `/api/state` and the line/source endpoints in `app/main.py`; update `tests/test_plc.py`, `tests/test_mqtt_source.py`, `tests/test_source_manager.py`, `tests/test_api.py` accordingly (`pytest tests/test_plc.py tests/test_mqtt_source.py tests/test_source_manager.py tests/test_api.py -q`).
- [x] 3.2 Implement OEE connection state and endpoints in `app/main.py`: `POST /api/oee/connection` (build DSN to `oee` db, test with `SELECT 1`, store server-side, error on failure), `GET /api/oee` (latest row, "not connected" error payload), `GET /api/oee/history?minutes=N`; remove `POST /api/oee/reset` and `PUT /api/oee/ideal-cycle-time`; verify with `tests/test_oee_api.py` rewritten against a fake DB layer (`pytest tests/test_oee_api.py -q`).
- [x] 3.3 Remove the now-unused `ideal_cycle_time` helpers from `app/db.py` and delete `tests/test_db_ideal_cycle.py`; verify `pytest tests -q` passes.

## 4. Dashboard UI

- [x] 4.1 Rebuild the OEE panel in `app/static/index.html`: four percentage tiles fed by `GET /api/oee`, Chart.js OEE trend line from `GET /api/oee/history`, "—" when not connected, error state on unreachable DB; remove state badge, counts row, Ideal Cycle Time editor, Reset button, and timestamp display; verify by loading the dashboard with no connection (tiles show "—").
- [x] 4.2 Add the connection bar (IP, Port, User, Password + Connect button) with localStorage persistence and auto-reconnect on page load, showing visible errors on failure; verify manually: connect to a running `oee` database, reload the page, confirm auto-reconnect; confirm a bad password shows an error and keeps the previous connection.
- [x] 4.3 Rewrite the footer limitations text (persistence model, recorder independence, no state machine, momentary-pulse caveat) and update `README.md` with the two-process deployment shape (recorder + local Postgres per line PC, roaming dashboard); verify docs match the final `.env.example` and endpoints.

## 5. Verification

- [x] 5.1 Full test suite: `.\.venv\Scripts\python.exe -m pytest tests -q` passes.
- [x] 5.2 End-to-end smoke test: run `scripts/init_db.py`, start `python -m app.recorder` against the PLC (or a simulated reader), confirm rows landing in `oee.oee` every second; start the dashboard, connect to the local database via the input bar, confirm tiles and trend chart populate; stop the recorder and confirm the dashboard shows the error/"—" state on next unreachable poll rather than appearing live.
