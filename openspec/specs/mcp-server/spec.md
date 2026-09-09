# mcp-server Specification

## Purpose

Exposes the line's live I/Q tag data and latest OEE figures to chatbots and external AI agents through the MCP protocol, served by the dashboard backend over Streamable HTTP so MCP clients such as n8n's MCP Client Tool can call read-only tools without any browser or dashboard UI involvement.

## Requirements

### Requirement: MCP streamable HTTP transport endpoint
The dashboard backend SHALL serve an MCP server using the Streamable HTTP transport at a single fixed endpoint on the same host and port as the dashboard HTTP API. The endpoint SHALL be unauthenticated. An MCP client SHALL be able to discover the server's tools and call them over this endpoint.

#### Scenario: MCP client connects
- **WHEN** an MCP client (e.g. n8n's MCP Client Tool with the HTTP Streamable transport) connects to the dashboard host's MCP endpoint
- **THEN** the session is established without credentials and the client can list the available tools

#### Scenario: Same process as the dashboard
- **WHEN** the dashboard server is running
- **THEN** the MCP endpoint is reachable on the same host and port as the dashboard HTTP API, with no additional process started, and the dashboard HTTP routes are unaffected

### Requirement: get_iq_data tool
The MCP server SHALL provide a `get_iq_data` tool that returns the current I/Q data: a boolean value for each of the 14 PLC tags from the active data source's latest snapshot (direct PLC or MQTT), together with the connection status (`connected`, `stale`), the active source, and the connection identity (PLC IP or broker address). Each tag value SHALL be accompanied by its description so an agent can interpret the tag's meaning.

#### Scenario: Live tag snapshot returned
- **WHEN** `get_iq_data` is called while the dashboard has an active, connected data source
- **THEN** the tool returns the 14 tag booleans matching the dashboard's current view, with connection status, source, connection identity, and per-tag descriptions

#### Scenario: Disconnected source
- **WHEN** `get_iq_data` is called while the active data source is not connected (or not yet configured, e.g. MQTT before a broker address is submitted)
- **THEN** the tool returns a response clearly indicating the disconnected/connecting state rather than fabricated tag values

### Requirement: get_latest_oee tool
The MCP server SHALL provide a `get_latest_oee` tool that returns the latest OEE row (`timestamp`, `availability`, `performance`, `quality`, `oee`) read from the `oee` database at `OEE_DATABASE_URL`. The MCP server's OEE access SHALL use `OEE_DATABASE_URL` exclusively and SHALL NOT depend on or affect the dashboard's UI-connected OEE database state.

#### Scenario: Latest OEE row returned
- **WHEN** `get_latest_oee` is called while the `oee` database at `OEE_DATABASE_URL` is reachable and contains rows
- **THEN** the tool returns the most recent row's timestamp and the four percentages

#### Scenario: Database unreachable or unconfigured
- **WHEN** `get_latest_oee` is called and `OEE_DATABASE_URL` is unset, or the database is unreachable, or the table contains no rows
- **THEN** the tool returns a readable error or empty-data payload instead of raising an error to the agent

### Requirement: Read-only MCP surface
The MCP server SHALL expose exactly the two read-only tools (`get_iq_data`, `get_latest_oee`) and no other tools. No MCP tool SHALL write to the PLC or modify any database.

#### Scenario: Tool inventory
- **WHEN** an MCP client lists the server's tools
- **THEN** exactly `get_iq_data` and `get_latest_oee` are available, and none of them can modify PLC or database state
