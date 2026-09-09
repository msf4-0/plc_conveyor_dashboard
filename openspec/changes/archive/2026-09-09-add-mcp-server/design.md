# Add MCP Server — Design

## Context

The dashboard backend (`app/main.py`) already owns all the data the MCP server needs: `poller.snapshot()` (the active source's tag booleans and connection status) and `latest_oee_row()` (`app/db.py`) against a PostgreSQL DSN. n8n's MCP Client Tool node speaks the legacy SSE transport (SSE GET + POST messages endpoint). See proposal.md for motivation and specs/mcp-server/spec.md for the behavior contract.

## Goals / Non-Goals

**Goals:**

- MCP server living inside the running dashboard process (no second service)
- SSE transport compatible with n8n's MCP Client Tool node
- Two read-only tools: `get_iq_data`, `get_latest_oee`
- OEE access decoupled from the dashboard UI's `_oee_conn` state

**Non-Goals:**

- Authentication on the MCP endpoints (matches the unauthenticated `/api/*` LAN posture; revisit if exposed beyond LAN)
- A third tool (counts/history) — the user story fixes the scope at two
- Any UI change, new PLC connection, or database write path

## Decisions

### D1: Official `mcp` SDK's FastMCP over the fastmcp 2.x package
Use `mcp.server.fastmcp.FastMCP` from the official `mcp` Python SDK (pinned `mcp<2`; the 2.x SDK renamed FastMCP to MCPServer). Its transport apps provide exactly what n8n needs — the Streamable HTTP endpoint comes from `.streamable_http_app()` at `settings.streamable_http_path` (default `/mcp`). Alternative fastmcp 2.x offers more features (OAuth, proxying, composability) we do not use and pulls a much larger dependency tree. Hand-rolling the protocol was rejected as unnecessary complexity.

### D2: Mount the Streamable HTTP app into the existing FastAPI app
`app.mcp_server` builds the FastMCP instance and exposes its Streamable HTTP Starlette sub-app; `app/main.py` mounts it at `/` **after** all dashboard routes are registered (mount-at-bottom) so the MCP endpoint lands at exactly `/mcp` without shadowing `/` or `/api/*`. Because mounted sub-app lifespans do not run in Starlette, the FastMCP session manager is run inside the dashboard's existing lifespan (`async with mcp_server.session_manager.run()` around the serving period). Same uvicorn process and port as the dashboard; startup/shutdown ride the existing lifespan. Alternative: a separate stdio server process — rejected because it would need its own PLC connection and could not mirror the dashboard's runtime source/broker switches. Note: an earlier iteration used the legacy SSE transport (`/mcp/sse` + `/mcp/messages`); it was replaced by Streamable HTTP because n8n deprecates SSE transport in its MCP Client Tool node.

### D3: `get_iq_data` delegates to the live SourceManager snapshot
The tool calls `poller.snapshot()` from `app/main.py` (same module state the dashboard uses), so it automatically reflects direct/MQTT mode and runtime broker switches. Tag descriptions come from `app.tags.TAGS`. When the snapshot's tag values are `None` (disconnected or inactive MQTT slot), the tool returns the connection state with no fabricated tag values. Note: the snapshot's existing `values` key holds the UI view (nested, 13 tags, button polarity applied); the tool reads the raw 14-tag map, so the direct and MQTT snapshots also carry a `raw` key (raw booleans, dashboard UI unaffected).

### D4: `get_latest_oee` reads `OEE_DATABASE_URL` directly, decoupled from `_oee_conn`
The MCP tool resolves its DSN from the `OEE_DATABASE_URL` environment variable via `app.config` (a new optional read in `load_config()`; unset means the tool reports "not configured" rather than failing startup, preserving the dashboard's no-DB fail-fast contract). It calls the existing `latest_oee_row()` and mirrors `/api/oee`'s error semantics: DB unreachable → readable error payload; empty table → "no OEE data recorded yet" payload. The dashboard's UI-connected `_oee_conn` is neither read nor written by the MCP server. Alternative: reuse `_oee_conn` — rejected per user decision; the MCP server must work without anyone having connected a DB in the UI.

### D5: Unauthenticated endpoints
No bearer token or auth check. Rationale: consistency with the existing `/api/*` routes and LAN-only deployment. n8n connects with plain endpoint URL + no headers.

### D6: Read-only surface by construction
Only two tools are registered on the FastMCP instance; both are pure reads. No write-capable tool exists to misconfigure, preserving the project's strict read-only PLC invariant.

## Risks / Trade-offs

- [n8n's MCP node historically used the deprecated SSE transport] → switched to Streamable HTTP, the transport n8n's current MCP Client Tool node uses; the official SDK's `.streamable_http_app()` is stable and requires only running the session manager lifespan.
- [Long-lived SSE connections through proxies/timeouts] → deployment is LAN-direct (n8n → dashboard), no intermediary expected; if a proxy is later introduced, its idle timeout must exceed n8n's session duration or be configured for SSE.
- [OEE queries on tool calls hit PostgreSQL synchronously in the event loop] → `latest_oee_row` uses a short connect timeout (5 s) and single-row SELECT; acceptable for interactive agent polling. If needed later, run in a worker thread.
- [Mounting a sub-app adds route surface] → mounted under a dedicated prefix; no existing route changes.

## Migration Plan

1. Add `mcp` to `requirements.txt`; install in the venv.
2. Add `app/mcp_server.py`; mount in `app/main.py`; extend `.env.example` (`OEE_DATABASE_URL` annotation for dashboard-process use).
3. Restart the dashboard; point n8n's MCP Client Tool at `http://<host>:<port>/mcp/sse`.
4. Rollback: remove the mount + module; no data or schema impact.
