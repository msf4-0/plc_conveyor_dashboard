# dashboard-auth Specification (delta)

## Purpose

Restricts the dashboard's HTTP data surface to authorized personnel using one shared password from `.env`: a login endpoint, a signed `HttpOnly` session cookie enforced by middleware, a logout endpoint, and the UI login overlay / logout button.

## ADDED Requirements

### Requirement: Shared-password login endpoint
The dashboard SHALL provide a login endpoint that accepts a password and compares it against `DASHBOARD_PASSWORD` using a constant-time comparison. A correct password SHALL establish a session by setting a signed session cookie; a missing or incorrect password SHALL be rejected with HTTP 401.

#### Scenario: Correct password logs in
- **WHEN** a client submits the password matching `DASHBOARD_PASSWORD` to the login endpoint
- **THEN** the response sets a signed session cookie and the client's subsequent dashboard requests succeed without re-entering the password

#### Scenario: Incorrect or missing password is rejected
- **WHEN** a client submits an incorrect password, or no password, to the login endpoint
- **THEN** the dashboard responds with HTTP 401 and sets no session cookie

### Requirement: Session cookie gate over the data surface
The dashboard SHALL enforce a valid session cookie on all data-bearing routes (`/api/*`). Static assets and the dashboard page itself SHALL remain servable without a session because they contain no line data. A request to a gated route without a cookie, with a cookie whose signature does not verify, or with an expired cookie SHALL be rejected with HTTP 401 and no data.

#### Scenario: Unauthenticated API call is rejected
- **WHEN** a client calls any `/api/*` route without a session cookie
- **THEN** the dashboard responds with HTTP 401 and the response body carries no line data

#### Scenario: Expired or tampered cookie is rejected
- **WHEN** a client presents a session cookie that is expired or whose signature does not verify
- **THEN** the dashboard treats the client as unauthenticated and responds with HTTP 401

#### Scenario: Valid cookie passes
- **WHEN** a client presents a valid, unexpired session cookie obtained by logging in
- **THEN** all `/api/*` routes respond normally without re-authentication

### Requirement: Session cookie properties
The session cookie SHALL be signed with a server-side secret derived from `DASHBOARD_PASSWORD` (so changing the password invalidates every outstanding session), SHALL be marked `HttpOnly` and `SameSite=Lax`, and SHALL expire after 12 hours.

#### Scenario: Cookie is not readable by scripts and expires
- **WHEN** the login endpoint sets the session cookie
- **THEN** the cookie carries `HttpOnly` and `SameSite=Lax` attributes and a 12-hour expiry, and a cookie signed with a secret derived from a different password fails verification

### Requirement: Logout endpoint
The dashboard SHALL provide a logout endpoint that clears the session cookie. After logout, calls to gated routes SHALL be rejected with HTTP 401 until the client logs in again.

#### Scenario: Logout invalidates the session
- **WHEN** a logged-in client calls the logout endpoint and then calls a gated route
- **THEN** the session cookie is cleared and the gated call is rejected with HTTP 401

### Requirement: UI login overlay and logout button
The dashboard UI SHALL detect an HTTP 401 from a gated call and display a password prompt overlay; a successful login SHALL dismiss the overlay and resume the dashboard. The UI SHALL provide a logout button that calls the logout endpoint and returns to the login overlay.

#### Scenario: Login overlay appears on 401
- **WHEN** the dashboard UI receives HTTP 401 from a gated API call
- **THEN** it shows the login overlay and line data is not rendered

#### Scenario: Logout button returns to the login overlay
- **WHEN** a logged-in user clicks the logout button
- **THEN** the UI calls the logout endpoint and shows the login overlay again

### Requirement: Fail-fast auth configuration
`DASHBOARD_PASSWORD` SHALL be required at dashboard startup. If it is missing, the dashboard SHALL fail to start with an error message that names the variable and points to `.env.example`, and SHALL NOT serve any gated route.

#### Scenario: Missing password stops startup
- **WHEN** the dashboard is started without `DASHBOARD_PASSWORD` set
- **THEN** startup fails with an error naming the missing variable
