# production-statistics Specification

## Purpose

Counts conveyor cycle completions and metal-detector detections from the process image, keeps the per-minute counts in the dashboard process's memory (never persisted; reset on restart and connection change), and visualizes them as per-minute bar charts over a rolling 10-minute window.

## Requirements

### Requirement: Cycle completion counting
The system SHALL count one conveyor cycle completion each time the green tower light P3 (Q0.6) transitions from FALSE to ON (rising edge). Per the line's cycle definition, this transition occurs after B3, then B2, then B1 have detected and the green light stays on until B1 stops detecting; the counter relies solely on the P3 rising edge and SHALL NOT duplicate-count while P3 remains ON.

#### Scenario: Cycle completes
- **WHEN** P3 transitions from OFF to ON
- **THEN** the cycle count increases by exactly one

#### Scenario: Green light remains on
- **WHEN** P3 stays ON until B1 stops detecting and the cycle completes
- **THEN** no additional cycle count is recorded until P3 turns OFF and ON again

### Requirement: Metal detection counting
The system SHALL count one metal detection each time the metal detector B4 (I1.0) transitions from FALSE to TRUE (rising edge).

#### Scenario: Metal object detected
- **WHEN** B4 transitions from FALSE to TRUE
- **THEN** the metal-detection count increases by exactly one

#### Scenario: Sustained detection
- **WHEN** B4 remains TRUE across multiple poll cycles for a single object
- **THEN** only one metal detection is counted for that detection event

### Requirement: Dashboard independence from panel Reset
The panel's Reset button (S3) is a PLC control only: it SHALL NOT reset or otherwise affect the dashboard's cycle or metal-detection counters.

#### Scenario: Reset button pressed
- **WHEN** the panel Reset button (S3) is pressed
- **THEN** the dashboard's counters are unchanged

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

### Requirement: Edge re-baseline across data sources
Regardless of data source, the first snapshot after the dashboard (re)connects, after a line switch, or after a stale period SHALL be used only to establish a baseline: no cycle or metal-detection counts SHALL be generated from it. Counts SHALL resume from the second snapshot onward.

#### Scenario: Baseline on line switch
- **WHEN** the user switches to a new line while its green light P3 is already ON
- **THEN** no cycle is counted from that first snapshot; a count occurs only when P3 later rises again

#### Scenario: Baseline after stale period
- **WHEN** snapshots resume after a stale period with P3 already ON
- **THEN** no cycle is counted until P3 turns OFF and rises again

### Requirement: Lost edges while disconnected
In MQTT mode, edge events occurring on the line while the dashboard is stale, disconnected, or pointed at another line are not counted and cannot be recovered. The system SHALL document this limitation.

#### Scenario: Edge during dashboard downtime
- **WHEN** a cycle completes on a line while the dashboard is stale or subscribed to a different line
- **THEN** that cycle is not recorded, and this limitation is stated in the dashboard documentation
