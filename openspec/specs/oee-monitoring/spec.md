# oee-monitoring Specification

## Purpose

Displays Overall Equipment Effectiveness (Availability × Performance × Quality) figures recorded by the per-line OEE recorder: the dashboard connects to a line's local PostgreSQL `oee` database (user-supplied IP, port, user, and password) and shows the latest percentages plus an OEE trend chart. The dashboard computes no OEE itself.

## Requirements

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
