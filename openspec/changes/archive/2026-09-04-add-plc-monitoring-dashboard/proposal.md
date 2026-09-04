## Why

The factory has no visibility into the live state of its manufacturing line: tower lights, push buttons, conveyor motion, and sensor detections can only be observed by physically walking to the control panel. A monitoring dashboard that reads the PLC process image over Ethernet — without any TIA Portal access or PLC program changes — gives operators at-a-glance awareness, and persisted statistics (conveyor cycle completions, metal detections) enable production tracking that does not exist today.

## What Changes

- Add a read-only dashboard application that connects to the Siemens S7-1200 PLC via the S7 protocol (PUT/GET is already enabled on the PLC) and polls the process image at ~500 ms.
- Display live state of the three tower lights (P1 Red, P2 Yellow, P3 Green), four push buttons (ESO, Stop S1, Start S2, Reset S3), conveyor motion (K1 motor relay), and the four sensors (B1, B2, B3 proximity; B4 metal detector).
- Count conveyor cycle completions (detected via the green tower light OFF→ON transition) and metal-detector detections (B4 rising edge), persisting them to a local PostgreSQL server.
- Display per-minute bar charts (rolling 10-minute window) for both counters.
- Freeze displayed values and show a "stale / connection lost" banner when PLC connectivity drops, recovering automatically on reconnect.
- Single-line scope for now; the connection configuration is kept external so more lines can be added later.
- No PLC-side changes; the dashboard is strictly a consumer of the process image defined in `plc_tags.csv`.

## Capabilities

### New Capabilities

- `plc-connectivity`: Connecting to the S7-1200 over Ethernet via S7/PUT-GET, polling the process image at ~500 ms, handling connection loss (stale banner + freeze + auto-reconnect).
- `line-state-monitoring`: Live display of tower lights, push buttons (including NC inversion for Stop/E-stop), conveyor motion, and sensor detection states.
- `production-statistics`: Cycle-completion and metal-detection counting, PostgreSQL persistence, and per-minute bar charts over a rolling 10-minute window.

### Modified Capabilities

(none — greenfield project, no existing specs)

## Impact

- **New code**: dashboard application (PLC client, state display UI, counter/event pipeline, chart views, PostgreSQL persistence layer).
- **New dependency**: an S7 communication library (e.g., snap7/python-snap7 or equivalent), a PostgreSQL driver/client, and a charting library.
- **Systems**: reads S7-1200 process image over Ethernet (read-only; PUT/GET already enabled); writes to PostgreSQL at `localhost:5432` (user `postgres`).
- **No changes** to the PLC program, TIA Portal project, or control panel hardware.
- **Known limitation**: momentary button presses shorter than the poll interval may not register (accepted).
