## Context

`add-mqtt-multi-line-monitoring` (implemented, verified, not yet archived) left the architecture with two interchangeable sources behind one snapshot contract:

- `PlcPoller` (direct): thread + `Snap7Reader` for the dashboard's own PLC; baseline on first poll.
- `MqttLineSource` (mqtt): paho subscriber for the selected line; `_baseline = True` at init and on `set_line()`.

`app/main.py` instantiates exactly one at import via `build_source(config)`; `config.data_source` is read at call time in `/api/line` (400 in direct mode) and in the stats default. Both sources persist events with `line_ip` to the same central Postgres, and `/api/stats?line_ip=` is already line-scoped.

The user chose **Option A**: `direct` always means the dashboard's own configured PLC; the toggle is "my line (Ethernet) ↔ remote lines (MQTT)".

## Goals / Non-Goals

**Goals:**
- Switch direct ↔ MQTT at runtime with no restart; `DATA_SOURCE` becomes the startup default only.
- Preserve the no-phantom-count invariant across source switches.
- Keep `PlcPoller`/`MqttLineSource` untouched; isolate the change in one orchestration layer + API + UI.

**Non-Goals:**
- Direct S7 connections to lines other than the dashboard's own configured PLC (Option B, rejected).
- Persisting the runtime source choice across restarts (startup always uses `DATA_SOURCE`).
- Concurrent direct + MQTT operation (one active source at a time).
- Changes to the MQTT protocol, publisher, broker, or DB schema.

## Decisions

- **D1 — New `SourceManager` wrapper; sources untouched.** `app/source_manager.py` holds `self._source`, exposes `snapshot()`, `start()`, `stop()`, `set_line()`, `switch(source_name, line_ip=None)`, and properties (`line_ip`, `source`, `lines`). `main.py` replaces `poller = build_source(config)` with a manager whose initial source is `config.data_source`. Rationale: both sources already satisfy the contract and re-baseline at start; wrapping beats refactoring them into a common base class. Alternative (make each source reconfigurable in place) rejected: reconnecting a paho client to a *different broker address* or re-pointing `Snap7Reader` is fiddlier than discarding and rebuilding, and a fresh instance inherits tested startup-baseline behaviour.
- **D2 — Switch = stop old, build new, start new; build failures never strand the dashboard.** `switch()` runs: `old.stop()` → construct new source → `new.start()`. If construction or start raises (e.g., bad broker config), the manager logs it, keeps the *old* source running (revert), and reports the failure to the API (409/400) — a failed switch must not leave the dashboard blank. Note the asymmetry with line switches (which clear state optimistically): a source switch changes the process topology, so atomicity is worth the extra step.
- **D3 — `POST /api/source` with body `{"source": "direct"|"mqtt", "line_ip": optional}`.** Validation: unknown source name → 400; `line_ip` provided must be in the `LINES` registry → else 404 (same rule as `/api/line`); `line_ip` defaults to the registry's first line / configured broker line. Response is the new snapshot (connecting state). Existing `POST /api/line` stays for switching lines *within* mqtt mode. `GET /api/state` keeps its shape; it now reflects whatever the manager exposes.
- **D4 — Stats default line comes from the manager.** `get_stats` uses `line_ip = query param or manager.line_ip or ""`. In direct mode that is `config.plc_ip`; in mqtt mode the selected line — satisfying "charts follow the active line" without touching `db.py`.
- **D5 — UI toggle beside the line dropdown.** The source badge becomes a two-button segmented control (DIRECT | MQTT); clicking posts to `/api/source`, then polls immediately. Line dropdown visibility follows the *active* source (not the env config). Poll loops and banners unchanged — the connecting/stale states already render the transition. Buttons disabled while a switch is in flight to prevent double-submits.
- **D6 — Count integrity is inherited, asserted in tests.** The manager does no edge bookkeeping; each fresh source baselines its first snapshot (existing behaviour). A test drives direct→mqtt→direct with fakes and asserts no events are produced from first snapshots while a signal is ON, and that a later genuine rising edge after the switch *is* counted (proves the new source is live, not just silent).
- **D7 — `main.py` module-level `poller` keeps its name** (test compatibility) but holds the `SourceManager`; existing stub-based API tests keep working because the manager quacks like a source. New tests use a manager over fake sources, and one over real `PlcPoller`/`MqttLineSource` with the fake reader + in-process broker.

## Risks / Trade-offs

- [paho network-loop thread lingering after `stop()` during a switch] → `MqttLineSource.stop()` already disconnects + `loop_stop()`; test asserts no callbacks fire after switch and that a *new* client instance is created per MQTT activation (no client reuse).
- [Snap7 connect failure on switch to direct] → `PlcPoller` retries continuously and reports `connected=False`; dashboard shows connecting→stale per existing behaviour; switch itself still succeeds (D2 only covers construction failures, and `PlcPoller` construction cannot fail).
- [Switch storms from UI double-clicks] → disabled buttons + server-side idempotence: switching to the already-active source is a no-op returning the current snapshot.
- [Events lost during the switch gap] → same accepted limitation as stale periods; documented already; re-baseline prevents phantom counts from masking it.
- [`DATA_SOURCE=mqtt` but user switches to direct with no PLC present] → behaves like today's direct mode with the PLC down (stale banner, retries); no special casing.
- [Delta applies only after change 1 is archived] → archive `add-mqtt-multi-line-monitoring` before applying this change (validate currently INFO-warns).

## Open Questions

- None. Option A was confirmed by the user; archive ordering is surfaced to the user with this proposal.
