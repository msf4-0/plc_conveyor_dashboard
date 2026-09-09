# PLC Conveyor Line Dashboard

**Reference Implementation for One of the Class Activity of MDEC TSP AI-Assisted Coding Course**

Read-only monitoring dashboard for Siemens S7-1200-controlled conveyor lines.
Reads the process image over Ethernet (S7 / PUT-GET) — or subscribes to an
MQTT broker whose address is typed into the dashboard — displays tower lights,
buttons, conveyor motion and sensors live, and counts cycle completions and
metal detections in memory with per-minute charts (rolling 10-minute window).
Count data is process-local: it resets when the dashboard restarts and when
the active connection (source or MQTT broker) changes. Multiple lines can be
monitored from one dashboard over MQTT, one broker at a time.
A standalone recorder process per line PC computes OEE for the directly
connected PLC and persists it to that PC's local `oee` PostgreSQL database;
the dashboard displays any line's OEE by connecting to its database.

## Architecture

**Direct mode** (`DATA_SOURCE=direct`, the original single-line setup):

```
+---------------------+        HTTP (~500 ms)        +-----------------------------------+
|  Browser (UI)       | <--------------------------> |  FastAPI backend (app/main.py)    |
|  app/static/        |   GET /api/state             |                                   |
|  index.html         |   GET /api/stats             |  +-----------------------------+  |
|  + Chart.js charts  |   POST /api/source           |  | PlcPoller thread (plc.py)   |  |
+---------------------+                              |  |  ~500 ms poll loop          |  |
                                                     |  +-------------+---------------+  |
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
                                                            +------------------+

Per-minute counts: the poller hands P3/B4 rising edges to the dashboard's
in-process MinuteCounter (app/stats.py) — no database is involved; counts
reset on dashboard restart and on source/broker switch.
```

**MQTT mode** (`DATA_SOURCE=mqtt`): each PLC line has a PC running a plain
MQTT broker (amqtt) and a publisher; the dashboard subscribes to whichever
broker address the user types into the header (one broker at a time).

```
Line PC (one per PLC)                             Dashboard PC
+-------------------------------+                 +-----------------------------------+
|  scripts/run_broker.py        |   plain MQTT    |  FastAPI backend (app/main.py)    |
|  (amqtt, no auth, :1883)      | <=============> |  MqttLineSource (mqtt_source.py)  |
|         ^                     |                 |   - subscribes "plc_tags"         |
|  app/publisher.py             |  JSON boolean   |   - strict 14-label payload       |
|   ~500 ms: Snap7Reader        |  tag map every  |   - stale when silent ~1 s        |
|   read-only, publishes the    |  poll interval  |   - edges -> in-memory MinuteCount|
|   14 tag booleans             |  (no retain,    |     (no status topic, no LWT)     |
+---------------+---------------+   no status)    +-----------------+-----------------+
                | Ethernet :102                                    |
        +------------------+                                      (no database:
        | Siemens S7-1200  |                                       counts are
        +------------------+                                     process-local)
```

Topic: `plc_tags` — a single fixed topic whose payload is a JSON object with
exactly the 14 labels from `plc_tags.csv` (`ESO, S1, S2, S3, B1, B2, B3, B4,
K1, K2, K3, P1, P2, P3`) mapped to booleans, e.g.
`{"ESO": true, "S1": false, ..., "P3": true}`. Snapshots are not retained and
nothing is published to a status topic: the dashboard judges liveness purely
by packet cadence and marks the connection stale after ~1 s of silence.

**OEE recording** (separate from the dashboard): each line PC also runs a
standalone recorder process that computes OEE for the PLC it is directly
connected to and persists history rows to its local PostgreSQL `oee` database,
regardless of what the dashboard does. The dashboard is a pure viewer: it
connects to any line's `oee` database (IP/port/user/password entered in the
UI, database name fixed to `oee`) and displays the latest Availability /
Performance / Quality / OEE figures plus an OEE trend chart.

```
Line PC (one per PLC)                                Any PC: dashboard
+-------------------------------------+              +-------------------------------+
|  app/recorder.py  (python -m        |              |  FastAPI backend (main.py)    |
|  app.recorder)                      |              |   POST /api/oee/connection    |
|   ~500 ms Snap7Reader (read-only)   |              |   GET  /api/oee (latest row)  |
|   -> OeeEngine (no state machine;   |              |   GET  /api/oee/history       |
|      counts B3/B1 cycles, P1 = stop)|              +---------------+---------------+
|   -> insert row every               |                              | read-only SQL
|      OEE_WRITE_INTERVAL_S (default 1 s)             +--------------v---------------+
+------------------+------------------+              |  PostgreSQL: oee db, table   |
                   |                                  |  oee {timestamp, availability,
          +------------------+                         |  performance, quality, oee}  |
          | Siemens S7-1200  |                         +-------------------------------+
          +------------------+
```

- **app/config.py** — loads `.env` (PLC IP/rack/slot, poll interval, `DATA_SOURCE`, the line-PC publisher's `BROKER_HOST`/`BROKER_PORT`); fails fast if missing/invalid. The dashboard requires no database configuration, and in MQTT mode no broker configuration either: the broker address is typed in the UI at runtime. `load_recorder_config()` is the recorder's own fail-fast loader (`OEE_DATABASE_URL`, `OEE_WRITE_INTERVAL_S`, `IDEAL_CYCLE_TIME_S` + the PLC settings); the recorder never requires the dashboard's variables.
- **app/tags.py** — tag map derived from `plc_tags.csv`; button polarity centralised here (S1/ESO normally-closed: pressed = LOW).
- **app/plc.py** — `Snap7Reader` (two byte-range reads per cycle: Inputs I0.0–I1.7, Outputs Q0.0–Q1.7) and `PlcPoller` (direct mode; freezes values + flags stale on connection loss, re-baselines on reconnect, delivers edge events to the dashboard's counter callback).
- **app/stats.py** — in-process per-minute counter (`MinuteCounter`): a thread-safe rolling 10-minute ring of 1-minute buckets for cycle/metal events; zero-filled `HH:MM` labels; reset on restart (memory) and connection change (wired by main.py). Counts are never persisted.
- **app/oee.py** — simplified OEE engine: cycle counting (B3 opens, B1 classifies via B2/B4 latches, open cycle counts as bad), run time while connected, stop time while the red tower light P1 is on, full pause + edge re-baseline while disconnected. No line state machine, no reset.
- **app/recorder.py** — standalone recorder (`python -m app.recorder`): polls the directly-connected PLC, appends a row to the local `oee` database every `OEE_WRITE_INTERVAL_S` (default 1 s), survives PLC and database outages, runs independently of the dashboard.
- **app/mqtt_proto.py** — the fixed `plc_tags` topic and its payload codec: a JSON object with exactly the 14 `plc_tags.csv` labels mapped to booleans (strict parse; unknown keys ignored).
- **app/broker.py** + **scripts/run_broker.py** — plain, no-auth MQTT broker for the line PC (amqtt).
- **app/publisher.py** — line-PC publisher: reads the PLC read-only and publishes the tag booleans to `plc_tags` at the poll interval; no retain flag, no status topic, no Last Will.
- **app/mqtt_source.py** — dashboard MQTT source: subscribes to the typed broker's `plc_tags` topic, decodes the label->boolean payload, detects edges (baseline-only on connect/switch/stale) and hands them to the dashboard's counter callback; stale after ~1 s of snapshot silence (there is no status topic).
- **app/edges.py** — rising-edge detection: P3 OFF→ON = cycle complete, B4 OFF→ON = metal detected; no duplicate while ON, no phantom edges after reconnect/switch.
- **app/source_manager.py** — owns the active data source (direct/MQTT) and the active broker address; an inactive MQTT slot reports "connecting" until an address is submitted, and submitting a different address rebuilds the source; forwards edge events to the counter and fires a connection-change hook (counter reset) after a successful source or broker switch.
- **app/db.py** — psycopg (v3) access to the `oee` database only (ensure schema, insert row, latest row, history window, connection test). Count events are not stored.
- **app/main.py** — FastAPI: serves the UI and `GET /api/state`, `GET /api/stats` (in-memory per-minute counts for the active connection), `POST /api/source` (switch sources; MQTT takes a `broker` address `IP` or `IP:port`, default port 1883), plus the OEE endpoints `POST /api/oee/connection` (test + activate a line's `oee` database), `GET /api/oee` (latest row), `GET /api/oee/history?minutes=`.
- **app/static/index.html** — single-page dashboard: tower-light LEDs, button pills (polarity pre-applied by the backend), conveyor state, sensor pills, stale/connecting banner, source toggle + typed MQTT broker input with Connect button (broker address persisted in browser localStorage), two Chart.js bar charts, and a database-backed OEE panel (tiles + trend chart + connection bar with browser localStorage persistence).

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env   # then edit values (PLC_IP etc.)
.\.venv\Scripts\python.exe scripts\init_db.py
```

`.env` values: PLC IP / rack / slot, poll interval, the HTTP host/port, and
the recorder settings (`OEE_DATABASE_URL`, `OEE_WRITE_INTERVAL_S`,
`IDEAL_CYCLE_TIME_S`) — see `.env.example`. The dashboard requires no database
configuration (counts are in-memory; the OEE panel takes its connection at
runtime from the UI) and no MQTT configuration either (the broker address is
typed in the dashboard and remembered in the browser's localStorage). `.env`
is gitignored; `.env.example` is the template.

### OEE recorder (line PC, one per PLC)

After `scripts/init_db.py` (it creates the `oee` database and table), start
the recorder on the PC that is directly connected to the PLC:

```powershell
# .env: PLC_IP / PLC_RACK / PLC_SLOT / POLL_INTERVAL_MS point at THIS line's PLC;
# OEE_DATABASE_URL points at the LOCAL PostgreSQL server's `oee` database;
# IDEAL_CYCLE_TIME_S is the Performance denominator (default 5 s).
.\.venv\Scripts\python.exe -m app.recorder
```

The recorder starts measuring the moment it starts (no start button or state
machine), survives PLC and database outages (the disconnected time is not
credited), and keeps running no matter what the dashboard does. Point the
dashboard's OEE panel at this PC's `oee` database (IP, port, user, password)
to see the figures.

### Line PC setup (MQTT mode, one per PLC)

On the PC next to each PLC, with the project + venv available:

```powershell
# .env: PLC_IP / PLC_RACK / PLC_SLOT / POLL_INTERVAL_MS point at THIS line's PLC;
# BROKER_HOST / BROKER_PORT point at the local broker (defaults 127.0.0.1:1883).
.\.venv\Scripts\python.exe scripts\run_broker.py    # window 1: MQTT broker (no auth)
.\.venv\Scripts\python.exe -m app.publisher         # window 2: publisher (read-only PLC reads)
```

The broker binds `0.0.0.0:<BROKER_PORT>` (default 1883) with anonymous
access — plain MQTT, no password, no TLS; do not expose it beyond the
lab/line network.

### Dashboard (MQTT mode)

In the dashboard's `.env` set:

```ini
DATA_SOURCE=mqtt
```

That is all: no broker is configured in the environment. The dashboard starts
in a "connecting" state; type the line's broker address (`IP` or `IP:port`,
default port 1883) into the header input and press Connect (or Enter). The
address is remembered in the browser's localStorage and auto-reconnected on
the next page load. `DATA_SOURCE=direct` (default) keeps the original
single-line S7 behaviour and hides the MQTT input.

### Switching sources at runtime

`DATA_SOURCE` only selects the **startup** source. While the dashboard is
running, the DIRECT | MQTT toggle in the header switches between them live
(REST: `POST /api/source` with `{"source": "direct"}` or
`{"source": "mqtt", "broker": "192.168.0.11[:1884]"}`). Semantics:

- `direct` always means the dashboard's **own** configured PLC
  (`PLC_IP`/`PLC_RACK`/`PLC_SLOT`) over the local Ethernet — never another
  line's PLC; use MQTT for the remote lines.
- In MQTT mode, submitting a **different broker address** (with or without a
  source switch) rebuilds the subscription: displayed values are cleared, the
  dashboard shows "connecting…", then live or stale data; each freshly started
  source re-baselines its first snapshot, so no phantom cycle/metal counts are
  produced by the change.
- A switch (source or broker) also **resets the per-minute counters**: the
  charts start from an empty window for the newly connected target. Counts are
  per-dashboard-process and are lost on restart by design.

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 in a browser.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Tests use a fake PLC reader (no PLC required) and an in-process MQTT broker
(no external broker required); only the OEE database tests require the local
PostgreSQL server.

## Known limitations

- **Momentary presses:** button presses shorter than the polling interval
  (~500 ms) may not register on the dashboard; the OEE recorder has the same
  blind spot for very short sensor pulses.
- **OEE is not dashboard state:** there is no line state machine, OEE reset,
  or Ideal Cycle Time editor in the dashboard. OEE figures come exclusively
  from the connected line's `oee` database; the Ideal Cycle Time is recorder
  configuration (`IDEAL_CYCLE_TIME_S` in the line PC's `.env`).
- **No OEE liveness signal:** if a line's recorder is stopped, its database
  simply stops receiving rows; the dashboard shows the last persisted figures
  without indicating staleness.
- **Credentials in the browser:** the OEE database connection entered in the
  UI is stored in the browser's localStorage in plain text (training-lab
  context).
- **Panel Reset:** the panel's Reset button is a PLC control only. It never
  resets the dashboard's cycle or metal-detection counters.
- **Stale data:** if the connection is lost (direct PLC link, or ~1 s of MQTT
  snapshot silence), the dashboard freezes the last values and shows a banner
  until updates recover.
- **Lost edges (MQTT mode):** counter events that occur while the dashboard
  is stale, disconnected, or pointed at another broker are not counted and
  cannot be recovered.
- **Counts are process-local:** per-minute counts live in the dashboard's
  memory only — they are lost on restart and reset when the active source or
  MQTT broker changes. Two dashboards watching the same broker report their
  own counts; nothing is buffered while the dashboard is down.
- **OEE history growth:** the recorder appends a row every
  `OEE_WRITE_INTERVAL_S` (default 1 s) forever; there is no retention job.

## Tag map

Derived from `plc_tags.csv`. Stop (S1) and Emergency Stop (ESO) are
normally-closed: "pressed" means the input reads LOW. Start (S2) and Reset
(S3) are normally-open. The E-stop polarity assumption was confirmed at
commissioning.
