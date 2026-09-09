# AGENTS.md

PLC conveyor line monitoring dashboard: Python 3 (FastAPI) backend serving a single-page UI, `python-snap7` (S7/PUT-GET, read-only) polling a Siemens S7-1200 at ~500 ms, in-memory per-minute counting (no count persistence; the dashboard requires no database configuration), Chart.js bar charts. A standalone OEE recorder process (`app/recorder.py`, `python -m app.recorder`) per line PC polls the directly-connected PLC and appends OEE history rows to that PC's local `oee` PostgreSQL database, independent of the dashboard; the dashboard is a pure OEE viewer that connects to any line's `oee` database. In MQTT mode the dashboard subscribes to the single fixed topic `plc_tags` (JSON map of the 14 `plc_tags.csv` labels to booleans) on a user-typed broker address; liveness is silence-based (~1 s), with no status topic, no retain, and no LWT.

## Commands

- All Python runs in the project venv: `.\.venv\Scripts\python.exe` (PowerShell).
- Install dependencies: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- Create/ensure the `oee` database + schema (recorder only): `.\.venv\Scripts\python.exe scripts\init_db.py`
- Run server: `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` → dashboard at http://127.0.0.1:8000
- Run OEE recorder (line PC): `.\.venv\Scripts\python.exe -m app.recorder`
- Tests (no PLC needed; only the OEE DB tests require PostgreSQL): `.\.venv\Scripts\python.exe -m pytest tests -q`
- Lint/typecheck: none configured — do not invent commands.

## Project layout & conventions

- `app/` — `config.py` (env, fail-fast; `load_config()` for the dashboard, `load_recorder_config()` for the recorder — each never requires the other's vars; the dashboard requires no database DSN and no MQTT broker config), `tags.py` (tag map from `plc_tags.csv`, button polarity: S1/ESO normally-closed), `plc.py` (poller thread, `Snap7Reader`, `on_event` callback), `edges.py` (P3→cycle, B4→metal rising edges), `stats.py` (in-process `MinuteCounter`: rolling 10-minute per-minute buckets, thread-safe, reset on restart/connection change; counts are never persisted), `mqtt_proto.py` (`plc_tags` topic + strict 14-label boolean payload codec), `publisher.py` (line-PC publisher: tag booleans to `plc_tags`, no retain/status/LWT), `mqtt_source.py` (dashboard subscriber: single `plc_tags` topic, silence-based liveness ~1 s), `source_manager.py` (active direct/MQTT source + typed broker address; inactive MQTT slot until an address is submitted; forwards events to the counter, fires the connection-change hook on source or broker switch), `oee.py` (simplified OEE engine: no line state machine, no reset; run time while connected, stop time while P1 red light is on; B3 opens a cycle, B1 classifies via B2/B4 latches), `recorder.py` (standalone OEE recorder loop), `db.py` (`oee` database access only — ensure schema, insert, latest, history, connection test), `main.py` (FastAPI + `/api/state`, `/api/stats` (in-memory counts for the active connection), `/api/source` (MQTT takes `broker: "IP[:port]"`), and the database-backed `/api/oee`, `/api/oee/connection`, `/api/oee/history`; there is no `/api/line`), `static/index.html` (dashboard UI: typed MQTT broker input + Connect, broker address in browser localStorage, DB-backed OEE panel + connection bar).
- There is NO line operating state machine, OEE reset, or Ideal Cycle Time editor in the dashboard; do not reintroduce them. Ideal Cycle Time is recorder configuration (`IDEAL_CYCLE_TIME_S` in `.env`, default 5, 0.1–3600).
- Count data is process-local: per-minute cycle/metal counts live in the dashboard's memory, reset on restart and when the active source or MQTT broker changes; do not reintroduce count persistence (no `DATABASE_URL`, no `line_events`).
- OEE table schema is fixed: database `oee`, table `oee`, columns `{timestamp, availability, performance, quality, oee}`; the dashboard connection dialog fixes the database name to `oee`.
- `.env` holds PLC IP/rack/slot, poll interval, the dashboard's HTTP host/port (`HOST`/`PORT`), recorder settings (`OEE_DATABASE_URL`, `OEE_WRITE_INTERVAL_S` default 1, `IDEAL_CYCLE_TIME_S`), `DATA_SOURCE` (`direct`/`mqtt`), and the line-PC publisher's broker endpoint (`BROKER_HOST`/`BROKER_PORT`); there are no MQTT broker or line-registry settings — the MQTT broker address is typed in the dashboard UI at runtime. `.env` is gitignored, `.env.example` is the template. Never commit `.env`.
- PLC access is strictly read-only (PUT/GET); never write to the PLC. The recorder writes only to the `oee` database.
- Counter events use rising edges with a re-baseline on (re)connect — no phantom counts. Same invariant applies to OEE accumulation: time/counts are never credited across a disconnect.

## Spec-driven workflow (OpenSpec)

Non-code work (proposals, specs, change plans) is managed by OpenSpec; do not edit `openspec/` contents by hand:

- Start a change: `/opsx-propose "<idea>"` — this creates `openspec/changes/<id>/` with proposal, specs, and tasks.
- Implement only against an approved change: `/opsx-apply <id>`.
- Archive completed work: `/opsx-archive <id>`; sync spec docs with `/opsx-sync`.
- Specs live in `openspec/specs/`, active changes in `openspec/changes/`, config in `openspec/config.yaml`.
- opencode integration files are in `.opencode/` (commands + skills); refreshing them is done by `openspec init --tools opencode`, not by hand.

## Environment

- Windows / PowerShell 5.1 shell — no `&&`; use `cmd1; if ($?) { cmd2 }`.
- Paths contain spaces; quote them.
- Node.js 24.x is installed; OpenSpec CLI is global (`openspec --version` → 1.12.0).
