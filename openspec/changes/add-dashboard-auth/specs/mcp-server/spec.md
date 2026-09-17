# mcp-server Specification (delta)

## MODIFIED Requirements

### Requirement: MCP streamable HTTP transport endpoint
The dashboard backend SHALL serve an MCP server using the Streamable HTTP transport at a single fixed endpoint on the same host and port as the dashboard HTTP API. The endpoint SHALL require a bearer token: requests MUST carry `Authorization: Bearer <MCP_TOKEN>` where `MCP_TOKEN` is configured in `.env` (required at startup, fail-fast). Requests without the token or with a wrong token SHALL be rejected with HTTP 401 before reaching the MCP server. Dashboard session cookies SHALL NOT be honored on this endpoint. An MCP client configured with the token SHALL be able to discover the server's tools and call them over this endpoint.

#### Scenario: MCP client connects
- **WHEN** an MCP client (e.g. n8n's MCP Client Tool with the HTTP Streamable transport) connects to the dashboard host's MCP endpoint carrying the correct `Authorization: Bearer` token
- **THEN** the session is established and the client can list the available tools

#### Scenario: Missing or wrong token is rejected
- **WHEN** a request reaches the MCP endpoint without the `Authorization` header, or with a token other than `MCP_TOKEN`
- **THEN** the dashboard responds with HTTP 401 and no MCP session is established

#### Scenario: Same process as the dashboard
- **WHEN** the dashboard server is running
- **THEN** the MCP endpoint is reachable on the same host and port as the dashboard HTTP API, with no additional process started, and the dashboard HTTP routes are unaffected

#### Scenario: Missing MCP_TOKEN stops startup
- **WHEN** the dashboard is started without `MCP_TOKEN` set
- **THEN** startup fails with an error naming the missing variable
