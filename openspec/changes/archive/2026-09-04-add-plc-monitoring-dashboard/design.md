## Context

Greenfield project: no code, no package manifest. The PLC side is fixed and read-only — the S7-1200 exposes a known process image (`plc_tags.csv`: 5 inputs in area I, 8 outputs in area Q), PUT/GET communication is already enabled, and no TIA Portal access exists. PostgreSQL 5432 is already running on localhost (user `postgres` / password `postgres`). Node.js 24.x is installed; the runtime stack itself is an open choice. See proposal.md for motivation and the three capability specs for required behavior.

## Goals / Non-Goals

**Goals:**
- One self-contained service that polls the PLC, detects counter edges, persists events to PostgreSQL, and serves the browser dashboard.
- Robust session handling: auto-reconnect, frozen values + stale banner on connection loss.
- Simple, local-dev-friendly configuration (PLC IP, DB DSN) in one place.

**Non-Goals:**
- Writing any value to the PLC; multi-line support (structure should not preclude it, but only one connection is built).
- K2/K3 direction/speed display; fault semantics for red/yellow lights beyond mirroring bits.
- Historical reporting beyond the rolling 10-minute per-minute charts; user authentication.
- Resetting counters from the dashboard (panel Reset is PLC-only and does not touch counters).

## Decisions

- **D1 — Stack: Python 3 + FastAPI backend serving a single-page frontend.** Rationale: `python-snap7` is the most battle-tested PUT/GET client for S7-1200; FastAPI serves both a JSON API and the static dashboard from one process; `psycopg` (v3) for PostgreSQL. Alternatives: Node.js (`node-snap7` — thinner community, bindings less maintained) or a separate Go/Rust service (overkill for one line). The browser cannot speak S7, so a backend is unavoidable regardless.
- **D2 — S7 reads: two reads per cycle (Inputs I0.0–I1.7, Outputs Q0.0–Q1.7), ~500 ms interval.** Both areas fit in one byte-range read each; mapping to named tags comes from a table derived from `plc_tags.csv`. Alternative: per-tag reads (14 round trips — wasteful) or optimizing with one combined area read (not possible across I and Q areas).
- **D3 — Edge detection in the backend poll loop.** Keep a previous-state snapshot per poll; emit a `cycle_complete` event on P3 FALSE→TRUE and a `metal_detected` event on B4 FALSE→TRUE. Rising-edge logic guarantees the "no duplicate while ON" requirement. On (re)connect, the first snapshot initializes the previous-state baseline and never emits edges, avoiding phantom counts after restarts or reconnects.
- **D4 — Persistence: single `line_events` table.** Columns: `id BIGSERIAL PK`, `event_type TEXT CHECK IN ('cycle_complete','metal_detected')`, `occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()`; index on `(event_type, occurred_at)`. One table (user asked for "an appropriately named table") keeps the schema minimal and makes per-minute aggregation a single `GROUP BY date_trunc('minute', occurred_at)` query. Alternative: two tables — rejected as needless duplication.
- **D5 — UI transport: browser polls a `/api/state` JSON endpoint at ~500 ms; no WebSocket.** At this rate, plain HTTP polling is simpler and adequate; the endpoint returns current values, connection status, and a server timestamp. Charts (Chart.js bar charts) poll `/api/stats` for per-minute counts over the last 10 minutes. Alternatives: WebSocket/SSE — rejected as unnecessary complexity for a 500 ms refresh on a single line.
- **D6 — Stale semantics: backend is the source of truth for staleness.** The poll loop catches comms errors, marks the session disconnected, and `/api/state` reports `connected: false` with the last-known values. The frontend freezes displayed values and shows the banner purely from that flag; it also greys the status if `/api/state` itself stops responding (backend down).
- **D7 — Button polarity centralized in the tag map.** Each tag entry carries its active level: S1 and ESO are NC (pressed = FALSE), S2/S3 are NO (pressed = TRUE). The backend exposes `pressed: true/false` per button so the frontend never handles inversion logic. ESO is assumed NC per standard practice — verify at commissioning.
- **D8 — Configuration via environment/`.env` + config file**: PLC IP, rack/slot (S7-1200 typically rack 0, slot 1), poll interval, DB DSN (`postgresql://postgres:postgres@localhost:5432/...`). Credentials are local-dev values supplied by the user; still kept out of source via `.env` (gitignored).

## Risks / Trade-offs

- [ESO polarity assumption (NC) is unverified] → Verify with a bench test at commissioning; changing polarity is a one-line tag-map edit (D7).
- [Momentary button presses shorter than the poll interval are missed] → Accepted and documented in the UI/docs per spec.
- [Dashboard and event timestamps use the dashboard PC clock] → Acceptable for a single-host deployment (PLC and dashboard co-located on the same PC per user); if lines ever span hosts, add NTP to deployment checklist.
- [PUT/GET is unauthenticated and the dashboard host can read the whole process image] → Read-only client; deployment restricted to the factory LAN; no write functions used anywhere in the codebase.
- [Missed DB writes during a PostgreSQL outage would lose counter events] → The poll loop retries inserts and logs failures; events between a failure and recovery are lost — accepted for v1, noted for future outbox-style buffering if statistics become critical.
- [If P3 blips (OFF→ON→OFF→ON) faster than one poll cycle, a cycle could be missed] → Cycle cadence is seconds-long versus 500 ms polling; accepted risk.

## Migration Plan

Greenfield: no migration. Deployment is (1) create database/schema (`line_events`), (2) configure `.env` with PLC IP/rack/slot, (3) run the service, (4) verify live values against the physical panel. Rollback is simply stopping the service; the PLC is untouched at all times.

## Open Questions

- PLC IP address and exact rack/slot — needed at first run; pure configuration values, captured in `.env` (task list includes obtaining them).
- Concrete dashboard database name on the local PostgreSQL instance — default proposed: `plc_dashboard`; trivially changeable in `.env`.
