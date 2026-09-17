## 1. Configuration

- [x] 1.1 Add `DASHBOARD_PASSWORD`, `MCP_TOKEN`, `MQTT_USERNAME`, `MQTT_PASSWORD` as required vars in `load_config()` (`app/config.py`), leaving `load_recorder_config()` unchanged; verify startup fails with a message naming the missing variable when each is absent (`python -m uvicorn app.main:app` without the var)
- [x] 1.2 Add the four new vars to `.env.example` with comments and to the local `.env`; verify `python -c "from app.config import load_config; load_config()"` succeeds with them set

## 2. Dashboard session auth

- [x] 2.1 Create `app/auth.py` with session-cookie sign/verify (`expiry_ts` + HMAC-SHA256 over a `sha256(DASHBOARD_PASSWORD)` secret) and unit tests for round-trip, expiry, tampered signature, and cross-password rejection (`pytest tests -q`)
- [x] 2.2 Add `POST /api/login` (constant-time password check, sets `HttpOnly; SameSite=Lax; Path=/; Max-Age=43200` cookie) and `POST /api/logout` (clears cookie) in `app/main.py`; verify 200/401 per spec scenarios with httpx TestClient tests
- [x] 2.3 Add the middleware gating `/api/*` with exemptions for `POST /api/login`, `POST /api/logout`, `/static/*`, and `/`; verify tests: gated route → 401 without cookie, 200 after login, 401 with expired/tampered cookie, static assets and `/` remain reachable
- [x] 2.4 Add login overlay (shown when a gated call returns 401, resuming polling after successful login) and header logout button to `app/static/index.html`; verify manually at http://127.0.0.1:8000: open without login → overlay; log in → dashboard; logout → overlay

## 3. MCP bearer token

- [x] 3.1 Extend the middleware to require `Authorization: Bearer <MCP_TOKEN>` on `/mcp` with constant-time compare and no session-cookie fallback; verify tests: 401 without token, 401 with wrong token, tool discovery succeeds with correct token (httpx TestClient against the mounted app)

## 4. MQTT broker auth + topic lock

- [x] 4.1 Verify the installed amqtt 0.11 auth and topic-check plugin config keys against its documentation, then update `app/broker.py` to reject anonymous connections with the shared credential and restrict topics to `plc_tags`; verify a config-level test asserts the Broker config contains the expected auth and topic-check entries
- [x] 4.2 Add `username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)` before connecting in `app/publisher.py` and `app/mqtt_source.py`; verify unit tests assert the credentials are set on the client before `connect`

## 5. Integration verification

- [x] 5.1 Run the full suite `pytest tests -q` and the live flow: run broker + publisher + dashboard from `.env` values, confirm anonymous MQTT CONNECT is refused, authorized publisher publishes, dashboard logs in via UI and shows live data, n8n MCP Client Tool with the bearer header lists tools
