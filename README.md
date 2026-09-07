# PLC Conveyor Line Dashboard

**Reference Implementation for One of the Class Activity of MDEC TSP AI-Assisted Coding Course**

Read-only monitoring dashboard for Siemens S7-1200-controlled conveyor lines.
Reads the process image over Ethernet (S7 / PUT-GET) — or subscribes to a
line's MQTT broker — displays tower lights, buttons, conveyor motion and
sensors live, and persists cycle-completion and metal-detection counts to
PostgreSQL with per-minute charts (rolling 10-minute window). Multiple lines
can be monitored from one dashboard over MQTT, one selected line at a time.

## Architecture

**Direct mode** (`DATA_SOURCE=direct`, the original single-line setup):

```
+---------------------+        HTTP (~500 ms)        +-----------------------------------+
|  Browser (UI)       | <--------------------------> |  FastAPI backend (app/main.py)    |
|  app/static/        |   GET /api/state             |                                   |
|  index.html         |   GET /api/stats             |  +-----------------------------+  |
|  + Chart.js charts  |   POST /api/line (MQTT mode) |  | PlcPoller thread (plc.py)   |  |
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
```

**MQTT mode** (`DATA_SOURCE=mqtt`, multi-line): each PLC line has a PC running
a plain MQTT broker (amqtt) and a publisher; the dashboard subscribes to the
selected line's broker.

```
Line PC xN (one per PLC)                          Dashboard PC
+-------------------------------+                 +-----------------------------------+
|  scripts/run_broker.py        |   plain MQTT    |  FastAPI backend (app/main.py)    |
|  (amqtt, no auth, :1883)      | <=============> |  MqttLineSource (mqtt_source.py)  |
|         ^                     |                 |   - subscribes plc/<ip>/state     |
|  app/publisher.py             |  retained JSON  |     + plc/<ip>/status (LWT)       |
|   ~500 ms: Snap7Reader        |  snapshots +    |   - decodes raw I/Q bytes with    |
|   read-only, publishes raw    |  LWT online/    |     app/tags.py (single truth)    |
|   I/Q bytes as hex            |  offline        |   - edges.py + db.py as in direct |
+---------------+---------------+                 +-----------------+-----------------+
                | Ethernet :102                                    | SQL
        +------------------+                             +----------------------+
        | Siemens S7-1200  |                             | PostgreSQL (central) |
        +------------------+                             +----------------------+
```

Topics: `plc/<line-ip>/state` (retained snapshot `{plc_ip, ts, inputs_hex,
outputs_hex}`) and `plc/<line-ip>/status` (retained `online`/`offline`; the
publisher registers `offline` as its Last Will).

- **app/config.py** — loads `.env` (PLC IP/rack/slot, poll interval, DB DSN, `DATA_SOURCE`, MQTT broker + `LINES` registry); fails fast if missing/invalid.
- **app/tags.py** — tag map derived from `plc_tags.csv`; button polarity centralised here (S1/ESO normally-closed: pressed = LOW).
- **app/plc.py** — `Snap7Reader` (two byte-range reads per cycle: Inputs I0.0–I1.7, Outputs Q0.0–Q1.7) and `PlcPoller` (direct mode; freezes values + flags stale on connection loss, re-baselines on reconnect).
- **app/mqtt_proto.py** — line topics (`plc/<ip>/state|status`) and the snapshot payload codec (hex-encoded raw I/Q bytes).
- **app/broker.py** + **scripts/run_broker.py** — plain, no-auth MQTT broker for the line PC (amqtt).
- **app/publisher.py** — line-PC publisher: reads the PLC read-only and publishes retained snapshots at the poll interval; retained `online`/`offline` status with an `offline` Last Will.
- **app/mqtt_source.py** — dashboard MQTT source: subscribes to the selected line, decodes snapshots with `tags.py`, detects edges (baseline-only on connect/switch/stale), persists events with the line's IP; stale on `offline` status or ~2 s of silence.
- **app/edges.py** — rising-edge detection: P3 OFF→ON = cycle complete, B4 OFF→ON = metal detected; no duplicate while ON, no phantom edges after reconnect/switch.
- **app/db.py** — psycopg (v3): `line_events` table (`id`, `line_ip`, `event_type`, `occurred_at`), event inserts, and the rolling 10-minute per-minute aggregation (filterable by line).
- **app/main.py** — FastAPI: serves the UI and `GET /api/state`, `GET /api/stats?line_ip=`, `POST /api/line` (switch lines, MQTT mode only).
- **app/static/index.html** — single-page dashboard: tower-light LEDs, button pills (polarity pre-applied by the backend), conveyor state, sensor pills, stale/connecting banner, line dropdown + source badge (MQTT mode), two Chart.js bar charts.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env   # then edit values (PLC_IP etc.)
.\.venv\Scripts\python.exe scripts\init_db.py
```

`.env` values: PLC IP / rack / slot, poll interval, `DATABASE_URL`
(`postgresql://postgres:postgres@localhost:5432/plc_dashboard`), the HTTP
host/port, plus the MQTT settings below. `.env` is gitignored; `.env.example`
is the template.

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
MQTT_BROKER_HOST=192.168.0.11      # broker of the default/selected line
MQTT_BROKER_PORT=1883
LINES=192.168.0.1=192.168.0.11:1883,192.168.0.2=192.168.0.12:1883
```

`LINES` is the dropdown registry: `PLC_IP=broker_host:port` pairs; the line is
identified by its PLC's IP. `DATA_SOURCE=direct` (default) keeps the original
single-line S7 behaviour and hides the dropdown.

### Switching sources at runtime

`DATA_SOURCE` only selects the **startup** source. While the dashboard is
running, the DIRECT | MQTT toggle in the header switches between them live
(REST: `POST /api/source` with `{"source": "direct"}` or
`{"source": "mqtt", "line_ip": "..."}`). Semantics (Option A):

- `direct` always means the dashboard's **own** configured PLC
  (`PLC_IP`/`PLC_RACK`/`PLC_SLOT`) over the local Ethernet — never another
  line's PLC; use MQTT for the remote lines.
- Switching clears the displayed values, shows "connecting…", then live or
  stale data; each freshly started source re-baselines its first snapshot, so
  no phantom cycle/metal counts are produced by the switch.
- The per-minute charts follow the active source's line (direct = the
  configured PLC's IP, MQTT = the selected line's IP).

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
(no external broker required); the database tests require the local
PostgreSQL server.

## Known limitations

- **Momentary presses:** button presses shorter than the polling interval
  (~500 ms) may not register on the dashboard.
- **Panel Reset:** the panel's Reset button is a PLC control only. It never
  resets the dashboard's cycle or metal-detection counters.
- **Stale data:** if the connection is lost (direct PLC link, or offline
  status / ~2 s of MQTT silence), the dashboard freezes the last values and
  shows a banner until updates recover.
- **Lost edges (MQTT mode):** counter events that occur while the dashboard
  is stale, disconnected, or pointed at another line are not counted and
  cannot be recovered.
- **Event storage:** counter events are written to PostgreSQL
  (`line_events` table, tagged with the line's PLC IP) using the dashboard PC
  clock. Events that occur while the database is unreachable are not buffered.

## Tag map

Derived from `plc_tags.csv`. Stop (S1) and Emergency Stop (ESO) are
normally-closed: "pressed" means the input reads LOW. Start (S2) and Reset
(S3) are normally-open. The E-stop polarity assumption was confirmed at
commissioning.
