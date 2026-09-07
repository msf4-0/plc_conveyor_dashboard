## 1. SourceManager core

- [x] 1.1 Create `app/source_manager.py`: `SourceManager` owning one active source; `start()`/`stop()`/`snapshot()`/`set_line()` delegation; properties `source`, `line_ip`, `lines`; factory `build_source(name, line_ip=None)` constructing `PlcPoller` (from `PLC_IP`/`PLC_RACK`/`PLC_SLOT`) or `MqttLineSource` (from `MQTT_BROKER_*` + registry) from the existing config; unknown name raises `ValueError`. Verify with unit tests over fake sources (delegation, property exposure, unknown-name error).
- [x] 1.2 Implement `switch(source_name, line_ip=None)`: no-op when already active (return current snapshot); on change, stop old source, build + start the new one, clear state via the new source's fresh instance; on construction/start failure, log, revert to the old source, re-raise. Verify with unit tests: switch swaps active source, no-op case, failure-revert case, old source's `stop()` called.

## 2. API wiring

- [x] 2.1 Update `app/main.py`: instantiate `SourceManager` (initial source = `config.data_source`; mqtt default line per existing rule) in place of the bare source, keeping the module-level name `poller` for test compatibility; `POST /api/source` body `{"source": "direct"|"mqtt", "line_ip": optional}` — 400 on unknown source, 404 on unknown registry line, current snapshot on success; no-op returns current snapshot; stats default line from the manager (`get_stats` reads `poller.line_ip`). Verify with httpx tests: valid switches (fake sources), invalid source 400, unknown line 404, stats default follows active source.
- [x] 2.2 Extend existing API tests (`tests/test_api.py`) so direct-mode stubs satisfy the manager contract; confirm `/api/line` still works in mqtt mode through the manager. Verify with `pytest tests/test_api.py -q`.

## 3. UI

- [x] 3.1 Update `app/static/index.html`: replace the source badge with a DIRECT | MQTT segmented toggle that posts `/api/source` and repolls state; line dropdown visibility follows the *active* source; disable the toggle (and dropdown) while a switch request is in flight; connecting/stale banners already cover transitions — verify banner text renders for both post-switch states. Verify the inline script with `node --check` and by booting the server in both startup modes and exercising the toggle via HTTP (`/api/state` reflects source switches; no browser automation needed; manual visual pass optional).

## 4. Count integrity & integration tests

- [x] 4.1 Add source-switch count-integrity tests with fakes: with P3 ON at switch time, neither the old source's last snapshot nor the new source's first snapshot produces an event; a genuine P3 rising edge after the new source is live IS counted (new source not dead). Verify in `tests/test_source_manager.py`.
- [x] 4.2 Add an end-to-end test (reuse `tests/conftest.py` broker fixture + fake reader): start in direct mode with an unreachable PLC, switch to MQTT (retained snapshot arrives, edges count with `line_ip` of the mqtt line), switch back to direct (stale/connecting, then stale while PLC unreachable; no events). Verify with `pytest tests/test_integration_mqtt.py tests/test_source_manager.py -q`.

## 5. Docs & full verification

- [x] 5.1 Update README: runtime source-switching section (toggle in the UI, `POST /api/source`, `DATA_SOURCE` is the startup default, Option A semantics — direct = dashboard's own PLC only). Verify docs match delivered API and env keys.
- [x] 5.2 Full verification: `.\.venv\Scripts\python.exe -m pytest tests -q` green; boot smoke test — direct startup, switch to MQTT (in-process broker + publisher), switch back to direct; confirm connecting/stale/states, stats following active line, and no phantom counts across switches.
