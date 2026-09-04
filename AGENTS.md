# AGENTS.md

PLC conveyor line monitoring dashboard: Python 3 (FastAPI) backend serving a single-page UI, `python-snap7` (S7/PUT-GET, read-only) polling a Siemens S7-1200 at ~500 ms, `psycopg` (v3) persisting events to PostgreSQL, Chart.js bar charts.

## Commands

- All Python runs in the project venv: `.\.venv\Scripts\python.exe` (PowerShell).
- Install dependencies: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- Create/ensure database + schema: `.\.venv\Scripts\python.exe scripts\init_db.py`
- Run server: `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` → dashboard at http://127.0.0.1:8000
- Tests (no PLC needed; DB required): `.\.venv\Scripts\python.exe -m pytest tests -q`
- Lint/typecheck: none configured — do not invent commands.

## Project layout & conventions

- `app/` — `config.py` (env, fail-fast), `tags.py` (tag map from `plc_tags.csv`, button polarity: S1/ESO normally-closed), `plc.py` (poller thread, `Snap7Reader`), `edges.py` (P3→cycle, B4→metal rising edges), `db.py` (`line_events` table), `main.py` (FastAPI + `/api/state`, `/api/stats`), `static/index.html` (dashboard UI).
- `.env` holds PLC IP/rack/slot, poll interval, DB DSN; `.env` is gitignored, `.env.example` is the template. Never commit `.env`.
- PLC access is strictly read-only (PUT/GET); never write to the PLC.
- Counter events use rising edges with a re-baseline on (re)connect — no phantom counts.

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
