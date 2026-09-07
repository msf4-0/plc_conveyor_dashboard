# plc-connectivity Delta

## ADDED Requirements

### Requirement: Selectable data source
The dashboard SHALL support two data sources selected by configuration: `direct` (a direct read-only S7 connection to the configured PLC, behaving exactly as before this change) and `mqtt` (subscribing to the MQTT broker of the selected line). The active source SHALL be indicated on the UI.

#### Scenario: Direct mode unchanged
- **WHEN** the data source is configured as `direct`
- **THEN** the dashboard polls the configured PLC over S7 as it did before this change

#### Scenario: MQTT mode subscribes to the selected line
- **WHEN** the data source is configured as `mqtt`
- **THEN** the dashboard subscribes to the selected line's broker and its displayed state derives from received MQTT snapshots

#### Scenario: Source shown on UI
- **WHEN** the dashboard is viewed
- **THEN** the UI indicates whether the current data source is direct or MQTT

### Requirement: Line registry and selection
In MQTT mode the dashboard SHALL hold a registry of known lines mapping each line's PLC IP address to its broker `host:port`, SHALL present these lines in a dropdown identified by PLC IP, and SHALL connect only to the selected line's broker. The dashboard SHALL also accept a directly configured broker address for MQTT mode even when the line is not in the registry.

#### Scenario: Lines listed for selection
- **WHEN** the dashboard runs in MQTT mode with a non-empty registry
- **THEN** the dropdown lists every registered line, identified by its PLC IP, and the currently selected line is highlighted

#### Scenario: Only the selected line is subscribed
- **WHEN** a line is selected in the dropdown
- **THEN** the dashboard subscribes only to that line's broker and ignores other lines

### Requirement: Line switching behaviour
When the user selects a different line, the dashboard SHALL unsubscribe from the previous line, clear the displayed values, show a "connecting…" state until the first snapshot of the new line arrives, and then show live or stale state as usual.

#### Scenario: Switch to an online line
- **WHEN** the user selects a new line whose broker and publisher are running
- **THEN** the previous line's values are cleared, a connecting state is shown briefly, and the new line's live state appears

#### Scenario: Switch to an unreachable line
- **WHEN** the user selects a line whose broker is unreachable
- **THEN** the previous line's values are cleared, a connecting state is shown, and the line becomes stale after the staleness timeout

### Requirement: MQTT liveness detection
In MQTT mode the dashboard SHALL mark the selected line stale when either its status topic reports `offline` or no new snapshot has arrived for a staleness timeout of approximately 2 seconds (four poll intervals). When `online` status or fresh snapshots resume, the stale state SHALL clear automatically.

#### Scenario: Publisher goes offline
- **WHEN** the line's status topic changes to `offline`
- **THEN** the dashboard shows the stale/disconnected state for that line

#### Scenario: Silent broker
- **WHEN** no snapshot has been received for approximately 2 seconds while status remains `online`
- **THEN** the dashboard shows the stale state

#### Scenario: Recovery
- **WHEN** fresh snapshots (or `online` status) resume after a stale period
- **THEN** the stale state clears and live values resume

## MODIFIED Requirements

### Requirement: S7 connection to the PLC
The system SHALL connect to the S7-1200 PLC over Ethernet using the S7 protocol (PUT/GET) and SHALL read the process image without writing to the PLC when the data source is `direct`. In `mqtt` mode the dashboard SHALL NOT connect to any PLC directly; it SHALL rely on the line-PC publisher instead.

#### Scenario: Successful connection
- **WHEN** the dashboard starts in `direct` mode and the PLC is reachable on the configured Ethernet address
- **THEN** the system establishes an S7 connection and begins reading the process image

#### Scenario: PLC unreachable at startup
- **WHEN** the dashboard starts in `direct` mode and the PLC cannot be reached
- **THEN** the system retries the connection continuously and shows the disconnected state on the UI

#### Scenario: No direct PLC connection in MQTT mode
- **WHEN** the dashboard runs in `mqtt` mode
- **THEN** it opens no S7 connection to any PLC and receives process-image data via MQTT only

### Requirement: Stale data handling on connection loss
The system SHALL freeze the last received values on screen and SHALL display a prominent "stale / connection lost" banner when the connection to the PLC is lost in `direct` mode, or when MQTT liveness signals staleness (offline status or snapshot silence) in `mqtt` mode. The system SHALL resume live updates automatically when the connection (direct) or fresh snapshots (MQTT) are re-established.

#### Scenario: Connection lost during operation
- **WHEN** the PLC connection drops while the dashboard runs in `direct` mode
- **THEN** the last received values remain displayed, a prominent stale/connection-lost banner is shown, and no values are updated from memory

#### Scenario: Automatic recovery
- **WHEN** the PLC becomes reachable again after a connection loss in `direct` mode
- **THEN** the stale banner is removed and live updates resume without user intervention

#### Scenario: Stale banner in MQTT mode
- **WHEN** the selected line becomes stale in `mqtt` mode
- **THEN** the last received values remain displayed with the same prominent stale banner
