## Why

Every dashboard HTTP route (including `POST /api/oee/connection`, which accepts a database password in the request body), the `/mcp` endpoint, and the line-PC MQTT broker (`0.0.0.0`, anonymous, any topic) are open to anyone on the network. An attacker on the LAN can read line data, point the dashboard's OEE panel at an arbitrary database, or publish a well-formed `plc_tags` payload to inject phantom cycle/metal counts into the dashboard's in-memory statistics.

## What Changes

- **BREAKING** Dashboard HTTP API requires login: one shared password from `.env` (`DASHBOARD_PASSWORD`), a login endpoint, a signed `HttpOnly` session cookie checked by middleware on all gated routes, and a logout endpoint. Unauthenticated API calls return 401.
- Dashboard UI shows a login overlay when a gated call returns 401, and a logout button in the header.
- **BREAKING** MCP endpoint `/mcp` requires `Authorization: Bearer <MCP_TOKEN>` (n8n MCP Client Tool node supports header auth). Dashboard session cookies are not honored on `/mcp`.
- **BREAKING** Line-PC MQTT broker rejects anonymous connections (`allow-anonymous=false`): one shared username/password from `.env` (`MQTT_USERNAME`/`MQTT_PASSWORD`), and a topic check that allows only `plc_tags`.
- Publisher (`app/publisher.py`) and dashboard MQTT subscriber (`app/mqtt_source.py`) send the shared MQTT credentials before connecting. The dashboard's typed-broker-address UI flow is unchanged; credentials are supplied silently from `.env`.
- All four new env vars are required (fail-fast at startup, same convention as `PLC_IP`). No TLS anywhere: LAN-only deployment, decided with the user. Session secret is derived in-app as `sha256(DASHBOARD_PASSWORD)` — changing the password invalidates all sessions, no extra env var.
- Non-goals: no per-user accounts, no TLS/HTTPS, no rate limiting on login, no changes to PLC access (stays read-only), recorder, OEE recording, or the `oee` database schema.

## Capabilities

### New Capabilities
- `dashboard-auth`: Shared-password login, session-cookie gate over the dashboard HTTP API, logout, and the UI login overlay / logout button.

### Modified Capabilities
- `mcp-server`: The MCP streamable HTTP endpoint changes from unauthenticated to requiring a bearer token (`MCP_TOKEN` from `.env`).
- `mqtt-line-transport`: The "Broker without authentication" requirement becomes broker authentication with one shared credential plus a topic lock restricting the broker to `plc_tags`; publisher and dashboard subscriber send credentials.

## Impact

- `app/config.py`: four new required env vars added to `Config`.
- New `app/auth.py` (session cookie sign/verify helpers); middleware and `/api/login` + `/api/logout` routes in `app/main.py`.
- `app/mcp_server.py` or the middleware path: bearer-token check on `/mcp`.
- `app/broker.py`: amqtt config — anonymous auth off, password plugin, topic-check restricted to `plc_tags`.
- `app/publisher.py`, `app/mqtt_source.py`: `username_pw_set(...)` before connecting.
- `app/static/index.html`: login overlay + logout button.
- `.env.example` updated with the four new required vars (`.env` stays gitignored).
- No new dependencies (stdlib `hmac`/`hashlib`); no database, PLC, or MQTT protocol changes beyond credentials.
