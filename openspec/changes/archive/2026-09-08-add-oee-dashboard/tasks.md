# Tasks: add-oee-dashboard

## 1. OEE engine core

- [x] 1.1 Create `app/oee.py` with the line state machine (NOT READY / READY / RUNNING / STOPPED, priority ladder, S2 exit from STOPPED — the S3 → NOT READY exit was added later in task 6.1, first-snapshot level baseline per design D3) and verify unit tests in `tests/test_oee_state.py` cover every scenario in `specs/line-operating-state/spec.md`
- [x] 1.2 Add cycle counting/classification to `OeeEngine` (B3 opens cycle + increments Total/In-flight, per-cycle B2/B4 flags, B1 classifies good/bad, new B3 while open force-classifies bad per design D4) and verify unit tests in `tests/test_oee_counts.py` cover every scenario in the "OEE cycle counting" and "Good/bad classification" requirements of `specs/oee-monitoring/spec.md`
- [x] 1.3 Add time accounting (wall-clock deltas from snapshot timestamps, Run Time from first READY entry inclusive of STOPPED, Stop Time in STOPPED, `on_disconnect` pause + reconnect re-baseline per design D2) and verify unit tests in `tests/test_oee_time.py` cover the "Run and stop time accumulation" and "Pause on disconnect" scenarios
- [x] 1.4 Add OEE metric computation (A, P, Q, OEE as percentages; "—" semantics when Run Time is zero) and `reset()` (zeros counts/timers/metrics only, never state machine or ideal cycle time) and verify unit tests cover the "OEE calculation", "OEE reset control", and "Line switch resets OEE" scenarios

## 2. Persistence: Ideal Cycle Time

- [x] 2.1 Add `ideal_cycle_time` table (line_ip PK, NUMERIC seconds, CHECK 0.1–3600) plus get/set helpers to `app/db.py` and extend `ensure_schema`; verify `scripts/init_db.py` still runs cleanly and a save/load round-trip test in `tests/test_db_ideal_cycle.py` passes
- [x] 2.2 Default to 5.0 s per line when no row exists and clamp/reject out-of-range values at the helper boundary; verify with the round-trip test's invalid-value case

## 3. API wiring

- [x] 3.1 Instantiate `OeeEngine` in `app/main.py`, feed it from `PlcPoller._process` (snapshot + timestamp) and its exception path (`on_disconnect`), and verify with a synthetic-snapshot integration test that events flow without changing existing `line_events` behavior
- [x] 3.2 Feed the engine from the MQTT source's per-snapshot processing path and verify the same pause/re-baseline behavior via a test with simulated snapshots (design D1/D6)
- [x] 3.3 Extend `GET /api/state` additively with `line_state` and `oee_paused`; verify the existing state payload fields are unchanged and new fields appear
- [x] 3.4 Add `GET /api/oee`, `PUT /api/oee/ideal-cycle-time` (Pydantic validation 0.1–3600, per active line_ip), and `POST /api/oee/reset`; verify with FastAPI TestClient tests for happy path, invalid input rejection (previous value retained), and reset semantics
- [x] 3.5 Trigger `engine.reset()` on `POST /api/line` and `POST /api/source` switches (design D6) and verify a test shows metrics zeroed after switching while the new line's persisted Ideal Cycle Time is loaded

## 4. Dashboard UI

- [x] 4.1 Add the state badge to the header of `app/static/index.html` (NOT READY grey / READY blue / RUNNING green / STOPPED red) driven by `/api/state` and verify visually at http://127.0.0.1:8000 with a mocked-source snapshot
- [x] 4.2 Add the OEE panel (A/P/Q/OEE tiles, Good / Bad incl. In-flight sub-count / Total, Run and Stop time) polling `/api/oee`, with "—" shown when run time is zero; verify with simulated `/api/oee` responses
- [x] 4.3 Add the Ideal Cycle Time input (default 5 s, inline range validation error) wired to `PUT /api/oee/ideal-cycle-time`, and the Reset button wired to `POST /api/oee/reset`; verify end-to-end against the running server
- [x] 4.4 Confirm the existing P3-based charts and indicator displays are unchanged and document the two limitations (in-memory OEE reset on restart; sub-poll-interval S2 presses may be missed) in the dashboard's documentation/help section

## 5. Final verification

- [x] 5.1 Run the full test suite `.\.venv\Scripts\python.exe -m pytest tests -q` and confirm all existing and new tests pass
- [x] 5.2 Run the server (`.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`), exercise state transitions/counts manually (or via mocked snapshots), and verify the dashboard shows badge, OEE panel, Ideal Cycle Time persistence across a server restart, and reset behavior

## 6. Panel reset (S3) → NOT READY + OEE reset

- [x] 6.1 Extend `OeeEngine._advance_state_locked` to observe the S3 (I0.3, normally-open) effective-press rising edge, evaluated before the S2 check so reset wins on a same-snapshot conflict: on S3 rising set state NOT READY, `_activated = False`, and perform the full OEE reset (counts/timers zeroed, Ideal Cycle Time kept) per revised design D3; verify unit tests in `tests/test_oee_state.py` cover the four new scenarios (S3 from READY/RUNNING, S3 from STOPPED, S3 while NOT READY, S3 beats S2 in the same snapshot)
- [x] 6.2 Add OEE-reset assertions for the S3 path (tests in `tests/test_oee_time.py`/`test_oee_metrics.py`): after S3 while metrics are non-zero, all counts/timers are zero, OEE is "—", the Ideal Cycle Time is retained, and the state is NOT READY; also verify the dashboard-only `POST /api/oee/reset` still leaves the state untouched
- [x] 6.3 Update the dashboard footer/help note (task 4.4 text) to mention that a panel Reset press returns the line to NOT READY and resets OEE, and that sub-poll-interval S3 presses may be missed; confirm the per-minute P3/B4 charts remain unaffected
- [x] 6.4 Rerun the full test suite `.\.venv\Scripts\python.exe -m pytest tests -q` and confirm all existing and new tests pass

## 7. Gate cycle counting on READY/RUNNING (revises GAP-010)

- [x] 7.1 Gate `_count_locked` in `app/oee.py` on the line state being READY or RUNNING: B3 rising edges in NOT READY/STOPPED open no cycle and change no counts; B1 rising edges in NOT READY/STOPPED classify nothing; a cycle opened in READY/RUNNING stays In-flight across a STOPPED period and classifies when B1 rises again in READY/RUNNING (per revised design D4); verify unit tests in `tests/test_oee_counts.py` replace the "counted in any state" scenario with NOT READY/STOPPED rejections plus a deferred-classification scenario
- [x] 7.2 Rerun the full test suite `.\.venv\Scripts\python.exe -m pytest tests -q` and confirm all existing and new tests pass
