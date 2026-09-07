## Why

The data source is currently fixed at process start by `DATA_SOURCE` in `.env`: the dashboard is either a direct S7 reader for its own line or an MQTT subscriber for remote lines, never both in one session. To supervise the dashboard's own line over the local Ethernet while keeping the other lines on MQTT, the user must edit `.env` and restart. A runtime toggle in the dashboard removes that restart and makes one dashboard serve both roles.

## What Changes

- Add a **`SourceManager`** that owns whichever data source is active (`PlcPoller` for direct, `MqttLineSource` for MQTT) and switches between them at runtime: stop the old source, build the new one from the existing `.env` configuration, start it, and delegate `snapshot()` to it.
- Add **`POST /api/source`** (`{"source": "direct" | "mqtt"}`) to switch sources at runtime; the choice no longer requires an app restart. `DATA_SOURCE` in `.env` becomes the **default source at startup**.
- **Option A semantics (confirmed)**: `direct` always means the dashboard's own configured PLC (`PLC_IP`/`PLC_RACK`/`PLC_SLOT`) — the toggle is "my line (Ethernet) ↔ remote lines (MQTT)". Direct connections to *other* lines' PLCs are explicitly out of scope.
- **UI**: the source badge becomes a **toggle** (DIRECT | MQTT) next to the line dropdown; the dropdown is visible only in MQTT mode. Switching sources clears values, shows "connecting…", then live/stale — the existing transition states.
- **Count integrity across source switches**: the first snapshot from a newly started source is baseline-only (no cycle/metal counts); both source types already re-baseline at startup, so the manager preserves the no-phantom-count invariant.
- **Stats follow the active line**: `/api/stats` default line becomes the active source's `line_ip` (direct = configured PLC IP, MQTT = selected line).

## Capabilities

### New Capabilities

- *(none)*

### Modified Capabilities

- `plc-connectivity`: The data source changes from "selected by configuration at startup" to "default from configuration, switchable at runtime from the dashboard" (direct = the dashboard's own configured PLC only), with defined transition behaviour (values cleared, connecting state, automatic re-baseline).

## Impact

- **New code**: `app/source_manager.py` (manager wrapping the active source; builds each source type from the existing config).
- **Modified code**: `app/main.py` (instantiate `SourceManager` instead of a single source; add `POST /api/source`; stats default line from active source), `app/static/index.html` (source toggle, transition handling), README (runtime switching section).
- **Unchanged**: `app/plc.py`, `app/mqtt_source.py`, `app/config.py` (env keys and parsing stay as-is; `DATA_SOURCE` remains the startup default), `app/db.py`, MQTT protocol, publisher/broker.
- **Tests**: new tests for `SourceManager` (switch direct→mqtt→direct with fakes, re-baseline across switches, stats line follows active source) and `/api/source` (accept/validate/reject cases); existing tests keep the no-PLC, no-external-broker guarantees.
- **Spec note**: this delta is written against the *post-*`add-mqtt-multi-line-monitoring` state of `plc-connectivity`; that change is implemented and verified but not yet archived, so the main spec does not yet contain "Selectable data source" — archiving it before this change keeps the delta apply clean.
