# PLC Conveyor Line Dashboard

**Reference Implementation for One of the Class Activity of MDEC TSP AI-Assisted Coding Course**

Read-only monitoring dashboard for a Siemens S7-1200-controlled conveyor line.
Reads the process image over Ethernet (S7 / PUT-GET), displays tower lights,
buttons, conveyor motion and sensors live, and persists cycle-completion and
metal-detection counts to PostgreSQL with per-minute charts (rolling
10-minute window).

## Architecture

```
+---------------------+        HTTP (~500 ms)        +-----------------------------------+
|  Browser (UI)       | <--------------------------> |  FastAPI backend (app/main.py)    |
|  app/static/        |   GET /api/state             |                                   |
|  index.html         |   GET /api/stats             |  +-----------------------------+  |
|  + Chart.js charts  |                              |  | PlcPoller thread (plc.py)   |  |
+---------------------+                              |  |  ~500 ms poll loop          |  |
                                                     |  +-------------+---------------+  |
                                                     |                |                  |
                                                     |     read I0.0-I1.7 / Q0.0-Q1.7    |
                                                     |                v                  |
                                                     |  +-----------------------------+  |
                                                     |  | Snap7Reader (python-snap7)  |  |
                                                     |  | S7 / PUT-GET, read-only     |  |
                                                     |  +-------------+---------------+  |
                                                     +----------------|------------------+
                                                                      | Ethernet :102
                                                                      v
                                                            +------------------+
                                                            | Siemens S7-1200  |
                                                            | (192.168.5.3)    |
                                                            +------------------+

  Poller loop: raw snapshot --> edges.py rising-edge detection (P3 -> cycle_complete,
  B4 -> metal_detected; re-baselined on (re)connect) --> db.py INSERT into PostgreSQL

  PostgreSQL (localhost:5432, db plc_dashboard, table line_events)
        ^                                              |
        |            per-minute aggregation query      v
        +------------------ app/db.py <----- GET /api/stats --> charts
```

- **app/config.py** — loads `.env` (PLC IP/rack/slot, poll interval, DB DSN); fails fast if missing.
- **app/tags.py** — tag map derived from `plc_tags.csv`; button polarity centralised here (S1/ESO normally-closed: pressed = LOW).
- **app/plc.py** — `Snap7Reader` (two byte-range reads per cycle: Inputs I0.0–I1.7, Outputs Q0.0–Q1.7) and `PlcPoller` (background thread; freezes values + flags stale on connection loss, re-baselines on reconnect).
- **app/edges.py** — rising-edge detection: P3 OFF→ON = cycle complete, B4 OFF→ON = metal detected; no duplicate while ON, no phantom edges after reconnect.
- **app/db.py** — psycopg (v3): `line_events` table (`id`, `event_type`, `occurred_at`), event inserts, and the rolling 10-minute per-minute aggregation.
- **app/main.py** — FastAPI: serves the UI and `GET /api/state` (live values + connection status) and `GET /api/stats` (per-minute counts).
- **app/static/index.html** — single-page dashboard: tower-light LEDs, button pills (polarity pre-applied by the backend), conveyor state, sensor pills, stale banner, two Chart.js bar charts.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env   # then edit values (PLC_IP etc.)
.\.venv\Scripts\python.exe scripts\init_db.py
```

`.env` values: PLC IP / rack / slot, poll interval, `DATABASE_URL`
(`postgresql://postgres:postgres@localhost:5432/plc_dashboard`), and the
HTTP host/port. `.env` is gitignored; `.env.example` is the template.

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 in a browser.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Tests use a fake PLC reader (no PLC required); the database tests require the
local PostgreSQL server.

## Known limitations

- **Momentary presses:** button presses shorter than the polling interval
  (~500 ms) may not register on the dashboard.
- **Panel Reset:** the panel's Reset button is a PLC control only. It never
  resets the dashboard's cycle or metal-detection counters.
- **Stale data:** if the PLC connection is lost, the dashboard freezes the
  last values and shows a banner until the connection recovers.
- **Event storage:** counter events are written to PostgreSQL
  (`line_events` table) using the dashboard PC clock. Events that occur while
  the database is unreachable are not buffered.

## Tag map

Derived from `plc_tags.csv`. Stop (S1) and Emergency Stop (ESO) are
normally-closed: "pressed" means the input reads LOW. Start (S2) and Reset
(S3) are normally-open. The E-stop polarity assumption was confirmed at
commissioning.
