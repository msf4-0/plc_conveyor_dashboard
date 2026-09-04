## 1. Project Setup

- [ ] 1.1 Initialize Python project (pyproject.toml/requirements.txt) with dependencies: fastapi, uvicorn, python-snap7, psycopg (v3), chart.js (vendored or CDN); verify `pip install` completes and `python -c "import snap7, psycopg, fastapi"` succeeds
- [ ] 1.2 Create `.env` template and gitignored `.env` with PLC IP, rack/slot, poll interval, and DB DSN (`postgresql://postgres:postgres@localhost:5432/plc_dashboard`); verify app loads config and fails fast with a clear message when values are missing
- [x] 1.3 Obtain the PLC's IP address and rack/slot from the user/PLC owner and record them in `.env`; verify a snap7 test read of IB0 succeeds against the real PLC (or a snap7 demo server when offline)

## 2. Database

- [x] 2.1 Create database `plc_dashboard` (if absent) and the `line_events` table per design D4 (`id`, `event_type` with CHECK constraint, `occurred_at` + index); verify with `\d line_events` or equivalent introspection query
- [x] 2.2 Implement a small DB access module (insert event, query per-minute counts for a rolling window) and verify with a round-trip unit test on the local PostgreSQL instance

## 3. PLC Connectivity (plc-connectivity spec)

- [x] 3.1 Implement tag map derived from `plc_tags.csv` (addresses, descriptions, active levels per design D7) and verify each named tag resolves to its correct I/Q byte.bit address via unit test
- [x] 3.2 Implement the ~500 ms poll loop reading Inputs I0.0–I1.7 and Outputs Q0.0–Q1.7, exposing the latest snapshot plus `connected` status; verify with a fake/real PLC that values refresh at the expected rate
- [x] 3.3 Implement reconnection with retry and stale flagging: on comms error mark disconnected and freeze last values, on reconnect re-baseline edge detection (no phantom edges); verify by interrupting/restoring connectivity in an integration test

## 4. Statistics Pipeline (production-statistics spec)

- [x] 4.1 Implement rising-edge detection on P3 (cycle_complete) and B4 (metal_detected) with previous-state snapshot, first-poll baseline, and no duplicate while ON; verify with a unit test driving synthetic snapshot sequences
- [x] 4.2 Persist each detected event as a timestamped row in `line_events`; verify events appear in the table during a simulated sequence
- [x] 4.3 Implement the per-minute aggregation query for the rolling 10-minute window for both event types; verify counts per minute match inserted test events (including minutes with zero events)

## 5. Dashboard UI (line-state-monitoring + production-statistics specs)

- [x] 5.1 Implement `/api/state` endpoint returning current values, per-button `pressed` (polarity pre-applied), and connection status; verify JSON against the tag map
- [x] 5.2 Implement `/api/stats` endpoint returning per-minute counts for the last 10 minutes for both counters; verify against DB test data
- [x] 5.3 Build the single-page dashboard: colored tower-light indicators (Red P1, Yellow P2, Green P3), button indicators (ESO, Stop, Start, Reset), Conveyor Running/Stopped from K1, and Detecting/Clear indicators for B1–B4; verify each indicator by toggling fake PLC values
- [x] 5.4 Add the stale/connection-lost banner: frontend freezes values and shows the banner when `connected: false`, hides it and resumes updates on recovery; verify by stopping/starting the PLC connection
- [x] 5.5 Add two Chart.js bar charts (cycles/min, metal detections/min) over the rolling 10-minute window with automatic window roll-forward; verify bars match `/api/stats` data
- [x] 5.6 Document the momentary-press limitation and panel-Reset independence in the UI footer or README; verify the text is visible/delivered
- [x] 5.7 Restyle UI per revised line-state-monitoring spec: circular glowing LEDs for tower lights (dim when off); retain pill badges for buttons/sensors with grey "RELEASED" text when released and "PRESSED" lit in colour when pressed (red E-stop/Stop, yellow Reset, green Start); colour the button label text the same way; metal-detector badge text lights red while detecting; verify visually in the browser against live PLC values

## 6. Integration Verification

- [x] 6.1 End-to-end test against the real PLC (or snap7 demo server): trigger the cycle sequence and confirm the green-light edge increments the cycle chart exactly once per cycle, and a metal object increments the detection chart
- [x] 6.2 Verify button polarity on the panel: Stop and E-stop show pressed when released/LOW, Start/Reset show pressed when held/HIGH; correct tag map if ESO polarity assumption proves wrong
- [x] 6.3 Verify dashboard restart preserves persisted counts and charts continue from the database history; verify counters are unaffected by pressing the panel Reset button
- [x] 6.4 Run `openspec validate add-plc-monitoring-dashboard` and resolve any reported issues
