# production-statistics delta

## MODIFIED Requirements

### Requirement: Per-minute statistics charts
The system SHALL display bar charts of counts per minute over a rolling 10-minute window for both the cycle-completion counter and the metal-detection counter, covering the currently active connection (the configured PLC in `direct` mode, the submitted broker address in `mqtt` mode). When the active connection changes, the charts SHALL start from an empty window for the new connection.

#### Scenario: Chart shows window
- **WHEN** the dashboard is viewed
- **THEN** each counter is shown as a bar chart of per-minute counts covering the last 10 minutes for the active connection

#### Scenario: Window rolls forward
- **WHEN** time advances past the current 10-minute window
- **THEN** the charts drop the oldest minute and include the newest minute

#### Scenario: Charts follow line selection
- **WHEN** the user switches the active data source or, in `mqtt` mode, submits a different broker address (the selected line)
- **THEN** the per-minute charts start from an empty window for the new connection and fill as new events are counted

### Requirement: Count reset on connection change
When the user switches the active data source (`direct` <-> `mqtt`) or, in `mqtt` mode, submits a different broker address, the dashboard SHALL reset the per-minute counters: the window for the newly connected target SHALL start empty, and counts observed for the previous connection SHALL NOT be shown for or attributed to the new one.

#### Scenario: Source switch resets counts
- **WHEN** the user switches from `mqtt` to `direct` (or vice versa) while counts are displayed
- **THEN** the per-minute charts restart from an empty window for the newly connected PLC

#### Scenario: Broker change resets counts
- **WHEN** the user submits a different broker address in `mqtt` mode
- **THEN** the per-minute counters are reset and the charts restart from an empty window for the newly connected broker
