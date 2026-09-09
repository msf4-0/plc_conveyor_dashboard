## Context

See proposal.md — Why. Today OEE is computed by a single in-memory `OeeEngine` (state machine + accumulators) owned by the dashboard process, fed by whichever source (`direct`/`mqtt`) is active, and lost on restart. The dashboard is one process (`app/main.py`) started with a fail-fast env config (`app/config.py`), PLC access is read-only snap7 (PUT/GET), PostgreSQL is accessed synchronously per-operation via psycopg v3 (`app/db.py`), and the UI is a single static page polling JSON endpoints.

## Goals / Non-Goals

**Goals:**
- OEE figures for the directly-connected PLC are persisted unconditionally, independent of the dashboard process, its UI activity, and its source/line switching.
- The dashboard can display any line's OEE by connecting to that line's `oee` database with a user-supplied IP/port/user/password.
- Remove all state-machine-driven OEE and line-state behavior from the dashboard.

**Non-Goals:**
- No central/multi-line OEE aggregation database; each line PC keeps its own local `oee` database.
- No authentication/authorization on the dashboard or the new endpoints (training-lab context, unchanged from today).
- No PLC writes anywhere; the recorder is read-only like everything else.
- No backfill or migration of historical OEE data (none exists — the old engine was in-memory).

## Decisions

### D1 — Standalone recorder process (chosen: separate process)
`python -m app.recorder` runs its own snap7 poll loop and writes to the local `oee` database. The dashboard process does not talk to the PLC for OEE purposes and does not need the recorder to be running (and vice versa).

*Alternative considered*: a background thread inside the FastAPI app — fewer processes, but recording would die with the dashboard, which contradicts "regardless of what the dashboard do".

### D2 — Simplified OEE engine (no state machine)
The recorder's engine keeps only the counting/timing core:
- Counting: B3 rising edge opens a cycle (no READY/RUNNING gating); B1 rising edge classifies it via the B2 latch and B4 latch (good iff B2 seen and B4 not seen since B3); an open cycle counts as bad (in-flight); a new B3 before B1 force-classifies the old cycle as bad — all identical to today's rules minus the state gating.
- Timing: Run Time accumulates from recorder start while the PLC is connected; Stop Time accumulates while P1 (red tower light) is TRUE. Availability = (Run − Stop)/Run.
- Disconnect: accumulation pauses entirely; the first snapshot after reconnect re-baselines edge detection only (preserves the no-phantom-counts invariant).

*Alternatives considered*: keep the full state machine in the recorder (rejected — the user wants recording to start immediately, with no button-edge state tracking); Availability ≡ 100% (rejected — P1 gives a meaningful availability for ~5 lines of logic).

The existing `OeeEngine` is replaced outright (state machine, reset, ideal-CT setter removed); the dashboard-side spec requirements move to the `oee-recording` capability.

### D3 — Persistence shape: append-only history
One row inserted every `OEE_WRITE_INTERVAL_S` (default 1 s ≈ 86,400 rows/day, trivial for Postgres):

```sql
CREATE TABLE IF NOT EXISTS oee (
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT now(),
    availability DOUBLE PRECISION,
    performance  DOUBLE PRECISION,
    quality      DOUBLE PRECISION,
    oee          DOUBLE PRECISION
);
```

Exactly the user-specified schema — no `line_ip` (the database itself identifies the line), no counts/run-stop columns (consequence: the dashboard cannot display them). NULLs when Run Time is zero. The database `oee` is created by `scripts/init_db.py` (connecting to the maintenance `postgres` database first — `CREATE DATABASE` cannot run inside a transaction) and the table by the recorder at startup (idempotent). The wall clock (UTC timestamptz) is used for row timestamps, not the monotonic clock used for accumulation.

*Alternative considered*: upsert of a single "latest" row — smaller, but loses the trend chart and any history.

### D4 — Recorder configuration is a separate fail-fast loader
A new `load_recorder_config()` in `app/config.py` requires only: `OEE_DATABASE_URL`, `OEE_WRITE_INTERVAL_S` (default 1), `IDEAL_CYCLE_TIME_S` (validated 0.1–3600, default 5), and the existing `PLC_IP`/`PLC_RACK`/`PLC_SLOT`/`POLL_INTERVAL_MS`. It does not require the dashboard's `DATABASE_URL`/`HOST`/`PORT`, so the two processes sharing one `.env` never demand each other's variables.

*Alternative considered*: one shared `Config` — would force the dashboard's vars on a line PC that only runs the recorder.

### D5 — Dashboard connection model: one server-side connection, browser-held credentials
`POST /api/oee/connection {ip, port, user, password}` builds DSN `postgresql://user:pass@ip:port/oee`, tests it (`SELECT 1`), and stores it in module-level state (one active connection at a time — single-user dashboard). `GET /api/oee` returns the latest row (or an error payload when not connected/unreachable); `GET /api/oee/history?minutes=N` returns trend rows. The browser persists the last connection parameters in `localStorage` and re-POSTs them on page load.

*Alternatives considered*: browser→Postgres direct (impossible from a browser); per-browser server-side sessions (overkill here).

### D6 — Dashboard OEE panel rebuild
Tiles (OEE/Availability/Performance/Quality) are fed from `GET /api/oee` on the existing 1 s poll; a Chart.js line chart shows OEE over the last ~10 minutes from `/api/oee/history`. Removed: state badge, counts row, Ideal Cycle Time editor, Reset button. No timestamp display on the panel (explicitly excluded). The Ideal Cycle Time input is not editable in the UI anymore — it is recorder configuration.

### D7 — Engine plumbing removal
`oee_engine` parameters are dropped from `PlcPoller`, `MqttLineSource`, and `SourceManager`; `line_state`/`oee_paused` disappear from `/api/state` and the line/source endpoints; `line-operating-state` capability requirements are all removed. Source/line switching, event persistence, and `/api/stats` are untouched.

## Risks / Trade-offs

- [OEE DB unavailable] → recorder logs insert failures and keeps polling/counting; rows are lost for the outage (no queueing — acceptable for a line PC where the DB is local).
- [Unbounded table growth] → 1 s cadence grows forever; acceptable per user decision; a retention job is out of scope (documented).
- [Credentials in browser localStorage] → plain-text on the user's machine; acceptable for the training-lab context, noted in docs.
- [Two processes share one `.env`] → separate config loaders (D4) prevent cross-requirements; documented in `.env.example` comments.
- [Dashboard shows stale DB when recorder is down] → the panel simply shows the last persisted row; docs note that a stopped recorder freezes the history (no liveness signal in the schema).
- [Momentary B3/B1/B2/B4 pulses shorter than the poll interval are missed] → pre-existing polling limitation, unchanged.

## Migration Plan

1. Run `scripts/init_db.py` (now also creates the `oee` database/table).
2. Fill the new `.env` values; start the recorder on each line PC (`python -m app.recorder`).
3. Deploy the dashboard; connect it to a line's `oee` DB via the new input bar.
4. Rollback: previous dashboard behavior is fully removed (breaking); rollback = revert the deployment; no data migration exists in either direction.

## Open Questions

None — all decisions were confirmed during exploration.
