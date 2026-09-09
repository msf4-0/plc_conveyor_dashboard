## Why

OEE currently lives only in the dashboard process's memory: it follows whichever source/line the dashboard has active, and everything is lost on restart. OEE must instead be recorded unconditionally by each line PC for the PLC that PC is directly connected to (via snap7), so the figures survive independently of the dashboard, and the dashboard should become a roaming viewer that can point at any line's OEE database.

## What Changes

- **BREAKING** — Add a standalone OEE recorder process (`python -m app.recorder`): its own snap7 poller for the directly-connected PLC, computing Availability / Performance / Quality / OEE and inserting a history row every `OEE_WRITE_INTERVAL_S` (default 1 s) into the local PostgreSQL database `oee`, table `oee`, schema `{timestamp, availability, performance, quality, oee}`. It runs regardless of what the dashboard does.
- The recorder uses a simplified OEE engine with **no line operating state machine**: recording starts the moment the recorder starts; Run Time accumulates while the PLC is connected; Stop Time accumulates while the red tower light P1 is on; cycle counting (B3 open / B1 classify with B2 and B4 latches) is ungated by line state. On PLC disconnect, accumulation pauses and edges re-baseline on reconnect (no phantom counts).
- The recorder's Ideal Cycle Time comes from `.env` (`IDEAL_CYCLE_TIME_S`, validated 0.1–3600 s, default 5).
- **BREAKING** — The dashboard's OEE panel becomes 100% database-backed: the in-memory `OeeEngine`, the OEE Reset control, the Ideal Cycle Time editor, the Total/Good/Bad/In-flight counts row, Run/Stop time display, and the line operating state badge are removed from the dashboard. The panel shows the four percentage tiles read from the connected OEE database, plus an OEE-over-time trend chart.
- New dashboard connection UI: user input bar for the OEE database (IP, Port, User, Password — database name fixed to `oee`), persisted in browser `localStorage` and auto-reconnected on page load.
- New backend endpoints: `POST /api/oee/connection` (test + store connection), `GET /api/oee` (latest row), `GET /api/oee/history` (trend rows). Removed endpoints: `POST /api/oee/reset`, `PUT /api/oee/ideal-cycle-time`.
- `.env` additions: `OEE_DATABASE_URL`, `OEE_WRITE_INTERVAL_S`, `IDEAL_CYCLE_TIME_S` (recorder-side; the recorder has its own fail-fast config loader so it does not require the dashboard's vars).
- `scripts/init_db.py` additionally creates the `oee` database (if missing) and the `oee` table.
- Line/source switching, `/api/state` (minus `line_state`/`oee_paused`), `/api/stats`, and `line_events` persistence are unchanged.

## Capabilities

### New Capabilities

- `oee-recording`: the standalone per-line OEE recorder process — simplified OEE computation (no state machine), history persistence to the local `oee` database at a fixed interval, disconnect pausing, and its `.env` configuration.

### Modified Capabilities

- `oee-monitoring`: the dashboard side is rewritten — OEE display becomes database-backed via a user-entered connection (IP, Port, User, Password; dbname `oee`, persisted in localStorage); the in-memory engine, Reset control, Ideal Cycle Time editor, counts/run-stop display, and the "restart clears OEE" limitation are removed.
- `line-operating-state`: the line operating state machine is deleted (no engine, no `/api/state` line_state field, no dashboard badge); all requirements of this capability are removed.

## Impact

- **Code**: new `app/recorder.py` (entry point + loop) and recorder config loader in `app/config.py`; rewritten `app/oee.py` (simplified engine); new OEE-database access functions in `app/db.py`; `app/main.py` (endpoint additions/removals); `app/plc.py`, `app/mqtt_source.py`, `app/source_manager.py` (drop `oee_engine` plumbing); `app/static/index.html` (panel rebuild + connection bar + localStorage); `scripts/init_db.py`.
- **APIs**: `/api/oee` redefined (DB-backed), `/api/oee/history` and `/api/oee/connection` added, `/api/oee/reset` and `/api/oee/ideal-cycle-time` removed, `/api/state` loses `line_state`/`oee_paused`.
- **Data**: new PostgreSQL database `oee` with table `oee` (`timestamp TIMESTAMPTZ`, four percentage columns); `ideal_cycle_time` table and its persistence become unused by the dashboard.
- **Deployment**: one recorder process + local PostgreSQL per line PC; dashboard requires no PLC or database of its own beyond what it connects to.
- **Tests**: `test_oee_*` rewritten for the simplified engine; `test_oee_state.py` and `test_db_ideal_cycle.py` deleted; API/source/poller/config tests updated.
- **Docs**: README and `.env.example` updated (recorder section, new deployment shape); dashboard footer limitations rewritten.
