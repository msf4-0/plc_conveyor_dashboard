# production-statistics delta

## MODIFIED Requirements

### Requirement: Per-minute statistics charts
The system SHALL display bar charts of counts per minute over a rolling 10-minute window for both the cycle-completion counter and the metal-detection counter, covering the currently active connection (the configured PLC in `direct` mode, the selected line in `mqtt` mode). When the active connection changes, the charts SHALL start from an empty window for the new connection.

#### Scenario: Chart shows window
- **WHEN** the dashboard is viewed
- **THEN** each counter is shown as a bar chart of per-minute counts covering the last 10 minutes for the active connection

#### Scenario: Window rolls forward
- **WHEN** time advances past the current 10-minute window
- **THEN** the charts drop the oldest minute and include the newest minute

#### Scenario: Charts follow line selection
- **WHEN** the user switches the active data source or, in `mqtt` mode, selects a different line
- **THEN** the per-minute charts start from an empty window for the new connection and fill as new events are counted

## ADDED Requirements

### Requirement: In-process per-minute counting
The dashboard SHALL own cycle-completion and metal-detection per-minute counting inside its own process, in memory: no cycle or metal-detection event or count SHALL be written to any database. Count history SHALL be process-local and SHALL NOT survive a dashboard restart: after a restart all per-minute counts start from zero.

#### Scenario: Counting without a database
- **WHEN** the dashboard counts cycle completions and metal detections while no PostgreSQL server is reachable or configured
- **THEN** the per-minute charts still show the counts collected since the dashboard started

#### Scenario: Restart resets counts
- **WHEN** the dashboard is restarted
- **THEN** the per-minute counts start from zero and previously observed counts are not restored

### Requirement: Count reset on connection change
When the user switches the active data source (`direct` <-> `mqtt`) or, in `mqtt` mode, selects a different line, the dashboard SHALL reset the per-minute counters: the window for the newly connected PLC SHALL start empty, and counts observed for the previous connection SHALL NOT be shown for or attributed to the new one.

#### Scenario: Source switch resets counts
- **WHEN** the user switches from `mqtt` to `direct` (or vice versa) while counts are displayed
- **THEN** the per-minute charts restart from an empty window for the newly connected PLC

#### Scenario: Line switch resets counts
- **WHEN** the user selects a different line in `mqtt` mode
- **THEN** the per-minute counters are reset and the charts restart from an empty window for the newly selected line

### Requirement: No configured database dependency
The dashboard SHALL start and operate fully without a configured PostgreSQL DSN: no database environment variable SHALL be required for the dashboard's own configuration. The OEE panel's runtime, user-supplied `oee` database connection (see `oee-monitoring`) SHALL be unaffected by this requirement.

#### Scenario: Dashboard starts without any database
- **WHEN** the dashboard is started with no database-related environment variable set
- **THEN** it serves the UI, PLC/MQTT state, per-minute statistics, and all OEE panel behaviour (given a runtime OEE connection) as usual

## REMOVED Requirements

### Requirement: Counter persistence in PostgreSQL
**Reason**: Count persistence is deliberately removed; the per-minute counts are now owned by the dashboard process in memory and intentionally reset on restart (see `In-process per-minute counting`).
**Migration**: None — losing count history across restarts is the accepted behaviour. Historical OEE figures remain persisted by the standalone recorder in the `oee` database (capability `oee-recording`) and are unaffected.

### Requirement: Line-scoped event persistence
**Reason**: Counts are no longer persisted, so there is no event storage to scope by line; the dashboard counts only the currently connected PLC (see `Count reset on connection change`).
**Migration**: Switching lines or sources starts an empty count window for the new connection; per-line count history is out of scope.
