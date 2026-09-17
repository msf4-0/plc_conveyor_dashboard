## Context

The dashboard is a FastAPI app (`app/main.py`) serving a single-page UI from `app/static/index.html`, with all state behind `/api/*` routes and an MCP streamable-HTTP sub-app mounted at `/`. The line-PC MQTT broker is amqtt (`app/broker.py`, anonymous, `0.0.0.0`); the publisher (`app/publisher.py`) and dashboard subscriber (`app/mqtt_source.py`) use paho-mqtt with no credentials. Configuration is fail-fast from `.env` via `app/config.py` (`load_config()` for dashboard/publisher, `load_recorder_config()` for the recorder — never requiring each other's vars). Deployment is LAN-only, plain HTTP, single shared-credential model chosen with the user (see proposal.md).

## Goals / Non-Goals

**Goals:**
- One shared password gates the dashboard HTTP data surface (`/api/*`), with login/logout endpoints and UI overlay/button.
- Bearer token gates `/mcp` for n8n/chatbot clients that can send an `Authorization` header.
- amqtt broker authenticates clients with a shared username/password and serves only `plc_tags`.
- All four new env vars are required, fail-fast, consistent with `PLC_IP` etc.

**Non-Goals:**
- Per-user accounts, user database, audit trails.
- TLS/HTTPS anywhere (LAN-only; revisit via a reverse proxy if exposure changes).
- Login rate limiting / lockout (LAN-only, shared credential).
- Changes to PLC access (stays strictly read-only), recorder, OEE recording, or the `oee` schema.

## Decisions

- **Stdlib-only auth: HMAC-signed cookie, no new dependency.** Cookie value = `expiry_ts.hex "." hex(hmac_sha256(secret, expiry_ts))`. Secret = `sha256(DASHBOARD_PASSWORD)`. Changing the password invalidates all sessions; no separate session-secret var to manage. Verification = recompute + `hmac.compare_digest` (also used for the password check and bearer token check). Alternatives rejected: itsdangerous (extra dep for the same thing), FastAPI LoginManager (extra dep, heavier), HTTP Basic (no login page — user asked for one — and awkward logout).
- **Cookie attributes:** `HttpOnly; SameSite=Lax; Path=/; Max-Age=43200` (12 h). No `Secure` flag — plain-HTTP LAN was explicitly chosen; adding it would silently break login.
- **Gate with one Starlette middleware on `/api/*`** rather than per-route dependencies: one place, covers future routes automatically. Exemptions: `POST /api/login`, `POST /api/logout`, `/static/*`, and `/` (the page itself serves only markup — no data leaks; `/api/state` returning 401 is the SPA's signal to show the login overlay). The MCP mount is covered separately (next decision).
- **Bearer check for `/mcp` in the same middleware**, by path prefix, before the sub-app is reached: `Authorization: Bearer <MCP_TOKEN>` required, constant-time compare, no session-cookie fallback (browsers never call MCP). Keeping it in the middleware means FastMCP's internals stay untouched. n8n's MCP Client Tool node supports header auth, so client-side is configuration only.
- **Login page as UI overlay, not a separate page.** `index.html` shows an overlay on 401 and retries after successful login; logout button calls `POST /api/logout` then shows the overlay. No redirect plumbing, no second HTML file, no server-side session store.
- **amqtt: `allow-anonymous=false` + password plugin + topic-check.** Exact amqtt 0.11 config keys (`auth` block with password file/plugin, `topic-check` with allow-list `plc_tags`) are verified against the installed amqtt version during implementation; a config-level test asserts the resulting config contains the expected keys. TLS is skipped (LAN-only; payload is public conveyor booleans; amqtt TLS setup is disproportionate).
- **paho credentials via `username_pw_set()`** in both `publisher.py` and `mqtt_source.py`, wired from `Config` (`MQTT_USERNAME`/`MQTT_PASSWORD`). Third-party open brokers ignore credentials, so the typed-broker-address UI flow keeps working unchanged.
- **Fail-fast config:** four new required vars read in `load_config()` (`DASHBOARD_PASSWORD`, `MCP_TOKEN`, `MQTT_USERNAME`, `MQTT_PASSWORD`). The recorder does not need any of them (`load_recorder_config()` unchanged). `.env.example` gains the four vars with comments.

## Risks / Trade-offs

- [Credentials travel over plain HTTP/MQTT on the LAN] → accepted deliberately (LAN-only decision); a reverse proxy with TLS is the upgrade path if exposure ever changes.
- [Shared password means no per-person accountability, and revocation = changing one `.env` value] → matches the user's chosen model; per-user accounts can be added later behind the same login endpoint shape.
- [No login rate limiting] → brute-force feasible only by LAN insiders; accepted at this threat level, revisit if the dashboard ever leaves the LAN.
- [amqtt plugin config is version-sensitive] → verify keys against the installed amqtt 0.11 during implementation; config-level test guards regressions.
- [Session cookie secret tied to password] → deliberate; rotation happens exactly when the password rotates. A future `SESSION_SECRET` var can override if needed.
