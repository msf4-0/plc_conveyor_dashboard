# Add MCP Server — Tasks

## 1. Setup

- [x] 1.1 Add `mcp` to `requirements.txt` and install into the venv (`.\.venv\Scripts\python.exe -m pip install -r requirements.txt`); verify `import mcp.server.fastmcp` succeeds
- [x] 1.2 Extend `.env.example` to document that the dashboard process also consumes `OEE_DATABASE_URL` for the MCP OEE tool; verify the file matches current `.env` conventions and `.env` itself stays untracked

## 2. MCP server module

- [x] 2.1 Create `app/mcp_server.py` with a FastMCP instance (official `mcp` SDK) exposing its SSE Starlette sub-app for mounting; verify the module imports cleanly
- [x] 2.2 Add `OEE_DATABASE_URL` as an optional field on the dashboard `Config` in `app/config.py` (unset = `None`, no fail-fast change); verify `load_config()` still succeeds without it
- [x] 2.3 Implement the `get_iq_data` tool delegating to the live `poller.snapshot()` from `app/main.py`, attaching per-tag descriptions from `app.tags.TAGS` and returning a clear disconnected/connecting payload when `values` is `None`; verify with a unit test using a fake snapshot
- [x] 2.4 Implement the `get_latest_oee` tool reading the configured `OEE_DATABASE_URL` and calling `latest_oee_row()`, with readable payloads for unset DSN, unreachable DB, and empty table; verify with unit tests for the unset/error branches (DB-backed branch optional per existing OEE DB test convention)

## 3. Integration

- [x] 3.1 Mount the MCP SSE sub-app in `app/main.py` under a dedicated prefix (e.g. `/mcp` → `/mcp/sse`, `/mcp/messages`); verify the dashboard routes (`/`, `/api/*`) are unchanged and the app starts
- [x] 3.2 Start the dashboard and connect n8n's MCP Client Tool node to the transport endpoint; verify the session establishes without credentials and the tool list shows exactly `get_iq_data` and `get_latest_oee`

## 5. Transport switch to Streamable HTTP (n8n deprecates SSE)

- [x] 5.1 Replace the SSE mount with the Streamable HTTP transport so the MCP endpoint is the single URL `/mcp`: use `streamable_http_app()`, run the FastMCP session manager inside the dashboard lifespan, and mount the sub-app after all dashboard routes; verify with an MCP streamable-HTTP client (list tools, call both tools) and `pytest tests -q`
- [x] 5.2 Verify n8n's MCP Client Tool node (transport type: HTTP Streamable) connects to `http://<dashboard-host>:<port>/mcp` without credentials and lists the two tools

## 4. Tests and validation

- [x] 4.1 Add tests covering the MCP tools: tool inventory (exactly the two read-only tools), disconnected-snapshot payload for `get_iq_data`, and the unset-DSN/error/empty branches for `get_latest_oee`; verify with `.\.venv\Scripts\python.exe -m pytest tests -q`
- [x] 4.2 Run the full test suite and confirm no existing tests regress; no lint/typecheck step (none configured)
