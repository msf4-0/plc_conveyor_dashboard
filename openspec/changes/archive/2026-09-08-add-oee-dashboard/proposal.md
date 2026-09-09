# Proposal: add-oee-dashboard

## Why

The dashboard currently shows raw line activity (per-minute counts, LED/button states) but no overall equipment effectiveness (OEE) KPIs, so operators and assessors cannot see availability, performance, or quality at a glance. This change adds an OEE calculation per the industry-standard methodology at https://www.oee.com/calculating-oee/, driven by a formal line operating state machine, and displays the results on the existing dashboard.

## What Changes

- Add a line operating state machine with four states — NOT READY, READY, RUNNING, STOPPED — derived from the start button (S2), reset button (S3), motor relay (K1), and red tower light (P1), and display the current state as a badge at the top of the dashboard.
- Count OEE cycles at the START sensor B3 rising edge (PX1) only while the line is READY or RUNNING — cycle start and end are both gated on those states — so unfinished parts still count toward Total Count; the existing P3-based `cycle_complete` counter and its chart remain unchanged.
- Classify each OEE cycle as good or bad when the part reaches the finish sensor B1 (PX3): good iff B2 and B1 were triggered since the B3 edge and the metal detector B4 was not triggered since the B3 edge; cycles not yet reaching B1 are shown as "In-flight" under Bad.
- Accumulate Run Time from the moment the line enters READY (in-memory, includes STOPPED time) and Stop Time while in the STOPPED state; pause accumulation during PLC/MQTT disconnects.
- Compute and display Availability = (Run Time − Stop Time) / Run Time, Performance = (Ideal Cycle Time × Total Count) / Run Time, Quality = Good / Total, and OEE = A × P × Q.
- Add a user-editable Ideal Cycle Time input (default 5 s, validated 0.1–3600 s) persisted server-side per line in PostgreSQL.
- Add a dashboard Reset control that zeros all OEE counts, timers, and accumulators without touching the line state machine; switching the selected line (`line_ip`) also performs a full OEE reset.
- Pressing the panel Reset button (S3) forces the line state machine to NOT READY (from READY, RUNNING, or STOPPED) and performs the same full OEE reset; the existing per-minute cycle and metal-detection counters remain unaffected by S3.
- OEE figures are intentionally in-memory only: they reset on dashboard restart (documented limitation).

## Capabilities

### New Capabilities

- `line-operating-state`: The line operating state machine (NOT READY / READY / RUNNING / STOPPED), its transitions, the state badge on the dashboard, and pause-on-disconnect semantics.
- `oee-monitoring`: OEE cycle counting (B3), good/bad classification (B2/B1/B4), run/stop time accumulation, OEE formulas, Ideal Cycle Time persistence, reset and line-switch behavior, and the OEE panel display.

### Modified Capabilities

- (none — the existing `production-statistics` P3-edge counter and charts, `line-state-monitoring` raw indicator displays, and `plc-connectivity` behavior are unchanged)

## Impact

- **New code:** `app/oee.py` (state machine + OEE accumulator, in-memory, per active line).
- **Modified code:** `app/main.py` (new/extended API endpoints), `app/db.py` (ideal cycle time table + helpers, schema migration), `app/config.py` (no change expected), `app/static/index.html` (state badge, OEE panel, Ideal Cycle Time input, Reset button).
- **Database:** new table for per-line Ideal Cycle Time; existing `line_events` table unchanged.
- **PLC:** strictly read-only as before — Ideal Cycle Time lives in the dashboard/DB, never the PLC.
- **Tests:** new pytest coverage for state machine, cycle classification, timers/pause, reset; existing tests unaffected.
