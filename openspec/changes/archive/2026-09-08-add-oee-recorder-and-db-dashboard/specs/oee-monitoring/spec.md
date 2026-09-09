## MODIFIED Requirements

### Requirement: OEE panel display
The dashboard SHALL display an OEE panel showing Availability, Performance, Quality, and OEE percentages, read from the currently connected OEE database's latest row. When no database is connected, the connection fails, or the database contains no rows, the tiles SHALL display "—". The panel SHALL also display a chart of OEE over a recent time window (approximately the last 10 minutes) from the connected database's history. The panel SHALL NOT display row timestamps. The existing per-minute count charts SHALL remain unchanged.

#### Scenario: Panel shows metrics
- **WHEN** the dashboard is connected to an OEE database that contains rows
- **THEN** the OEE panel shows the four percentages from the latest row, and the trend chart reflects the stored history

#### Scenario: No database connected
- **WHEN** no OEE database connection has been established
- **THEN** the OEE tiles show "—" and the trend chart is empty

#### Scenario: Connected database unreachable
- **WHEN** the connected OEE database becomes unreachable
- **THEN** the panel shows an error state and retains "—"/empty content rather than stale-looking live values

## ADDED Requirements

### Requirement: OEE database connection input
The dashboard SHALL provide a user input bar for connecting to an OEE database, with fields for IP address, port, user, and password; the database name SHALL be fixed to `oee`. On connect, the dashboard SHALL test the connection and show a visible error if it fails, leaving the previous connection state unchanged. A successful connection SHALL become the active OEE data source for the panel. The entered parameters SHALL be persisted in the browser's localStorage and automatically re-applied on page load.

#### Scenario: Successful connection
- **WHEN** the user enters valid IP, port, user, and password for a PostgreSQL server hosting the `oee` database and connects
- **THEN** the OEE panel begins displaying data from that database

#### Scenario: Failed connection
- **WHEN** the user enters unreachable or incorrect connection details
- **THEN** a visible error is shown and the previously connected database (if any) remains in effect

#### Scenario: Connection restored on reload
- **WHEN** the page is reloaded after a successful connection
- **THEN** the input bar is pre-filled from localStorage and the dashboard reconnects automatically

## REMOVED Requirements

### Requirement: OEE cycle counting at start sensor
**Reason**: Cycle counting moves to the standalone recorder (`oee-recording` capability) with state gating removed; the dashboard no longer computes OEE.
**Migration**: Run the recorder process on the line PC; the dashboard displays the recorder's persisted figures.

### Requirement: Good/bad classification at finish sensor
**Reason**: Moved to the recorder (state gating removed); the dashboard no longer computes OEE.
**Migration**: See the `oee-recording` capability's ungated cycle counting requirement.

### Requirement: Run and stop time accumulation
**Reason**: Moved to the recorder with new semantics (Stop Time from the P1 red light instead of a state machine).
**Migration**: See the `oee-recording` capability's run/stop time accumulation requirement.

### Requirement: Pause on disconnect
**Reason**: Applies to the recorder now; the dashboard no longer accumulates anything.
**Migration**: See the `oee-recording` capability's pause-on-disconnect requirement.

### Requirement: OEE calculation
**Reason**: Computation moved to the recorder (Availability now uses P1-based Stop Time).
**Migration**: See the `oee-recording` capability's OEE calculation requirement.

### Requirement: Ideal cycle time input and persistence
**Reason**: The Ideal Cycle Time is now recorder configuration via `IDEAL_CYCLE_TIME_S` in `.env`; the dashboard no longer offers an editor and the per-line `ideal_cycle_time` database persistence is retired.
**Migration**: Set `IDEAL_CYCLE_TIME_S` in the line PC's `.env` and restart the recorder.

### Requirement: OEE reset control
**Reason**: There is no dashboard-side accumulator to reset, and the recorder records unconditionally (no reset); S3-based full-reset behavior is also retired.
**Migration**: None — history rows simply continue; a new recording period can be started by restarting the recorder process.

### Requirement: Line switch resets OEE
**Reason**: The dashboard no longer owns an OEE accumulator; switching lines/sources does not affect any OEE figures.
**Migration**: Point the dashboard's OEE connection at the desired line's `oee` database instead.

### Requirement: In-memory OEE limitation
**Reason**: The limitation no longer exists: OEE is persisted to the recorder's database and survives dashboard restarts.
**Migration**: Update the dashboard documentation to describe the new persistence model.
