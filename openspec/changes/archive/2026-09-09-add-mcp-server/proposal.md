# Add MCP Server

## Why

A chatbot or external AI agent (n8n MCP Client Tool) needs read access to the line's live I/Q tag data and latest OEE figures. The dashboard's HTTP API targets browsers, not MCP clients; an MCP server exposes the same backend data through the MCP protocol so agents can query it with standard tool calls.

## What Changes

- Add an in-process MCP server mounted into the existing FastAPI app (same uvicorn process, same port) using the Streamable HTTP transport at a single endpoint (`/mcp`), compatible with n8n's MCP Client Tool node.
- Expose exactly two read-only MCP tools:
  - `get_iq_data` — current I/Q data: the 14 tag booleans from the active data source snapshot (direct PLC or MQTT), with connection status and tag descriptions.
  - `get_latest_oee` — latest OEE row (`timestamp`, `availability`, `performance`, `quality`, `oee`) read from the `oee` database at `OEE_DATABASE_URL`.
- The MCP server's OEE access uses `OEE_DATABASE_URL` exclusively; it does not depend on, read, or mutate the dashboard's UI-connected OEE database state (`_oee_conn`).
- The endpoints are unauthenticated (consistent with the rest of the backend's LAN posture).
- Add the `mcp` Python SDK to `requirements.txt`; extend `.env.example` to document `OEE_DATABASE_URL`'s new consumer (the dashboard process).
- No UI changes; no changes to existing endpoints or PLC access patterns (strictly read-only).

## Capabilities

### New Capabilities

- `mcp-server`: MCP protocol surface mounted in the dashboard backend — SSE transport endpoints, the two read-only tools (`get_iq_data`, `get_latest_oee`), their data sources, error payloads, and the read-only guarantee.

### Modified Capabilities

- (none)

## Impact

- **Code**: new `app/mcp_server.py` (FastMCP server + tools); `app/main.py` mounts the MCP SSE app; `app/config.py` optionally reads `OEE_DATABASE_URL` for the MCP tool without making it a dashboard fail-fast requirement.
- **Dependencies**: adds `mcp` (official Python SDK) to `requirements.txt`.
- **Config**: `.env.example` gains/annotates `OEE_DATABASE_URL` for dashboard-process use.
- **Systems**: same process and port as the dashboard; no second service to run. OEE reads go to the recorder's `oee` PostgreSQL database; PLC access remains via the existing poller only (no new PLC connection, no writes).
