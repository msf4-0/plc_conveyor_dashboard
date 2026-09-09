# Design: add-oee-dashboard

## Context

The dashboard polls the S7-1200 process image at ~500 ms (`PlcPoller`, `app/plc.py`), detects rising edges (`app/edges.py`), persists `cycle_complete`/`metal_detected` events to PostgreSQL (`app/db.py`), and serves a snapshot via `/api/state` through `SourceManager` (direct/mqtt). The UI (`app/static/index.html`) renders LEDs, buttons, sensors, and two per-minute charts. See proposal.md for motivation; behavior contracts are in `specs/line-operating-state/` and `specs/oee-monitoring/`.

Key constraints that shape the design:
- PLC access is read-only; the Ideal Cycle Time must live in the dashboard/PostgreSQL.
- Disconnects already freeze the poller's last values and set `connected=False`; the first snapshot after reconnect re-baselines edge detection (no phantom counts). OEE must follow the same discipline.
- `SourceManager` rebuilds the source on switch, which re-baselines the new source; OEE reset-on-line-switch must hook the same moment.
- OEE metrics are intentionally in-memory (per user decision): reset on restart, paused on disconnect.

## Goals / Non-Goals

**Goals:**
- A single, testable in-process OEE engine (state machine + counters + timers) fed one snapshot per successful poll.
- OEE panel and state badge on the dashboard with minimal disruption to existing endpoints/UI.
- Ideal Cycle Time persisted per `line_ip` in PostgreSQL.

**Non-Goals:**
- No historical OEE reporting, no shift scheduling, no planned-downtime categories.
- No per-line OEE history (accumulators exist only for the currently selected line; switching resets).
- No PLC writes, no debounce/filtering of sensor edges (per user decision), no changes to the existing P3-based counter or charts.

## Decisions

### D1: OEE engine as a standalone module fed by the poller loop
Create `app/oee.py` with a pure, thread-safe `OeeEngine` class. `PlcPoller._process` (and the MQTT source's equivalent loop) calls `engine.on_snapshot(raw: dict[str, bool], now: float, connected: bool)` for every successful poll, and `engine.on_disconnect()` when a poll fails. Rationale: both sources already own the poll/edge/re-baseline lifecycle; routing snapshots through one engine keeps state-machine, counting, and timing rules in one testable place with no PLC dependency (tests feed synthetic snapshots). Alternative considered: computing OEE on-demand in `/api/oee` from stored events — rejected because run/stop time and in-flight cycle state are not derivable from the current event table and the user chose in-memory accumulation anyway.

### D2: Time accounting from poll timestamps, not tick counting
The engine stores the timestamp of the last successful snapshot. Each successful `on_snapshot` adds `now - last_ts` to Run Time (always, once READY has been entered at least once) and to Stop Time when the current state is STOPPED. `on_disconnect` records the pause point; on the next successful snapshot the first one only re-baselines (no time credited for the gap). Rationale: wall-clock deltas give correct durations regardless of poll jitter; re-baselining the gap implements "pause on disconnect" without extra machinery. Alternative: counting polls × interval — rejected as inaccurate under jitter and reconnect delays.

### D3: State machine inside the engine with explicit priority
States: `NOT_READY` → (S2 rising edge) → `READY`; in READY: `RUNNING` while K1 TRUE; `STOPPED` while P1 TRUE (priority over RUNNING). From STOPPED an S2 rising edge returns to READY; an **S3 (panel reset, I0.3, normally-open) rising edge forces NOT READY from READY, RUNNING, or STOPPED** — evaluated *before* the S2 rising-edge check so reset wins if both edges land in the same poll snapshot. S2/S3 presses use the same effective (polarity-corrected) press state as `button_pressed` in `app/tags.py`. The engine observes the S3 edge itself in `on_snapshot` (no new API endpoint): on S3 rising it sets `_activated = False`, state `NOT_READY`, and performs the full OEE reset (zeroing counts/timers, keeping the Ideal Cycle Time). Startup/reconnect baseline: derive the state from the first snapshot's instantaneous levels (P1 on → STOPPED, K1 on → RUNNING, else READY — a first snapshot with S2 not pressed but the line running still lands in RUNNING/RUNNING-equivalent only if levels say so; we map levels directly since NOT READY is a dashboard-uptime concept, not a PLC one). Rationale: NOT READY is defined by the story as "dashboard just started, start button not pressed yet"; after a restart mid-run, showing the physically observed state is more truthful than NOT READY. Alternative: always start in NOT READY — rejected as misleading when the line is physically running.

### D4: Cycle classification with per-cycle sensor memory
On each B3 rising edge the engine opens a cycle record `{b2_seen, b4_seen}` and increments Total (and In-flight). While a cycle is open, B2/B4 rising edges set their flags (B2 seen = TRUE; B4 seen = TRUE → bad). On the B1 rising edge with a cycle open: good iff `b2_seen and not b4_seen`; close the cycle (Good/Bad += 1, In-flight -= 1). If a new B3 edge arrives while a cycle is still open, the old cycle is force-classified as bad (part never reached B1 cleanly — it cannot be good without B1). **Cycle start (B3 rising) and cycle end (B1 classification) are both gated on the line state being READY or RUNNING** — edges in NOT READY or STOPPED open/classify nothing; a cycle opened in READY/RUNNING stays In-flight across a STOPPED period and classifies when B1 rises again in READY/RUNNING. Rationale: per-cycle flags prevent a B4 event from a previous part leaking into the next cycle, matching spec GAP-003 decision A; the READY/RUNNING gate (revising the original GAP-010 decision) keeps manual parts pushed while the line is down out of the OEE figures. Alternative: time-window based attribution — rejected as fragile under poll quantization.

### D5: Ideal Cycle Time in a new PostgreSQL table
New table `ideal_cycle_time (line_ip TEXT PRIMARY KEY, seconds NUMERIC NOT NULL CHECK (seconds BETWEEN 0.1 AND 3600))`, created in `ensure_schema`. API: `GET/PUT /api/oee/settings` (or fold into `/api/oee` payload). Validation via Pydantic (0.1–3600, default 5.0). Rationale: server-side persistence per line was explicitly chosen; NUMERIC avoids float surprises; a dedicated table avoids touching `line_events`. Alternative: localStorage — rejected (not shared across viewers, chosen against).

### D6: API surface
- `GET /api/state` — extended with `line_state` (string) and `oee_paused` (bool) so the badge can sit next to existing UI; payload stays backward compatible (additive fields only).
- `GET /api/oee` — returns `{availability, performance, quality, oee, good, bad, in_flight, total, run_time_s, stop_time_s, ideal_cycle_time_s, line_state}`; "—" handled client-side when `run_time_s == 0`.
- `PUT /api/oee/ideal-cycle-time` — body `{seconds}`; validates and persists per active `line_ip`.
- `POST /api/oee/reset` — zeros accumulators; state machine untouched (dashboard control only).
- Panel reset S3 — observed as a rising edge by the engine inside `on_snapshot` (D3); it performs the full OEE reset AND forces NOT READY. No API endpoint involved; an S3 press that falls entirely within one poll interval can be missed (same known limitation as the other buttons).
- Line switch (`POST /api/line`, `POST /api/source`) — `SourceManager.switch`/`set_line` invoke `engine.reset()` after the new source is active.

Rationale: additive extension of existing endpoints; the engine instance lives at module scope in `main.py` (like `poller` today) and is shared with sources via a callback/wiring helper.

### D7: UI panel
`index.html` additions: state badge in the header (colour-coded: grey NOT READY, blue READY, green RUNNING, red STOPPED); an OEE panel with four percentage tiles (A, P, Q, OEE), count chips (Total, Good, Bad incl. "In-flight: n"), Run/Stop time read-outs, the Ideal Cycle Time input with inline validation error, and a Reset button. Poll `/api/oee` on the same cadence as `/api/state`. Existing charts untouched.

## Risks / Trade-offs

- [500 ms poll can miss very short S2/S3 presses → line never leaves NOT READY, or a panel reset is never observed] → Same known limitation as the existing button display (already documented); the documentation note covers both the state machine's Start button and the panel-reset OEE trigger.
- [Force-classifying an in-flight cycle as bad on a new B3 edge may mislabel slow parts] → Only triggers when a new part enters before the previous reached B1 (physically impossible on a single-part line at ideal cycle 5 s); conservative direction (understates Quality).
- [In-memory OEE lost on restart] → Accepted and documented per user decision (VR-7); Ideal Cycle Time is the only persisted OEE input.
- [`main.py` growing another module-scoped singleton and wiring] → Keep `OeeEngine` self-contained and wiring behind a small helper in `app/oee.py`; no framework introduction for this scale.
- [MQTT source must call the same engine hooks] → Both sources route through equivalent per-snapshot processing; tasks include verifying the MQTT path feeds the engine (its `_process` equivalent) so pause/re-baseline semantics match.
