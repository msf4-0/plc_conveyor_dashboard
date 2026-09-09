# plc-connectivity delta

## MODIFIED Requirements

### Requirement: Stale data handling on connection loss
The system SHALL freeze the last received values on screen and SHALL display a prominent "stale / connection lost" banner when the connection to the PLC is lost in `direct` mode, or when the MQTT connection has been silent for longer than the staleness timeout in `mqtt` mode. The system SHALL resume live updates automatically when the connection (direct) or fresh snapshots (MQTT) are re-established.

#### Scenario: Connection lost during operation
- **WHEN** the PLC connection drops while the dashboard runs in `direct` mode
- **THEN** the last received values remain displayed, a prominent stale/connection-lost banner is shown, and no values are updated from memory

#### Scenario: Automatic recovery
- **WHEN** the PLC becomes reachable again after a connection loss in `direct` mode
- **THEN** the stale banner is removed and live updates resume without user intervention

#### Scenario: Stale banner in MQTT mode
- **WHEN** the connected broker's snapshots stop arriving in `mqtt` mode
- **THEN** the last received values remain displayed with the same prominent stale banner

### Requirement: Selectable data source
The dashboard SHALL support two data sources: `direct` (a direct read-only S7 connection to the configured PLC, behaving exactly as before this change) and `mqtt` (subscribing to a user-supplied MQTT broker address). The startup source SHALL be selected by configuration (`DATA_SOURCE`), and the active source SHALL be switchable at runtime from the dashboard. The active source SHALL be indicated on the UI.

#### Scenario: Direct mode unchanged
- **WHEN** the data source is configured as `direct`
- **THEN** the dashboard polls the configured PLC over S7 as it did before this change

#### Scenario: MQTT mode subscribes to the selected line
- **WHEN** the data source is configured as `mqtt` and a broker address has been submitted
- **THEN** the dashboard subscribes to the submitted broker (the selected line) and its displayed state derives from received MQTT snapshots, ignoring all other brokers

#### Scenario: Source shown on UI
- **WHEN** the dashboard is viewed
- **THEN** the UI indicates whether the current data source is direct or MQTT

#### Scenario: Source switchable at runtime
- **WHEN** the user requests the other source from the dashboard while it is running
- **THEN** the dashboard switches data sources without requiring an application restart

### Requirement: Runtime source switching
The dashboard SHALL allow switching the active data source between `direct` and `mqtt` at runtime without an application restart. `direct` SHALL always mean a read-only S7 connection to the dashboard's own configured PLC (`PLC_IP`/`PLC_RACK`/`PLC_SLOT`); direct connections to other lines' PLCs are out of scope. Switching sources SHALL stop the previous source, start the requested one from the supplied configuration (for `mqtt`, the submitted broker address), clear the displayed values, show a "connecting…" state until the new source delivers data (or stale, if it cannot), and indicate the active source on the UI. The startup source SHALL remain the `DATA_SOURCE` configuration value.

#### Scenario: Switch from direct to MQTT at runtime
- **WHEN** the user requests the `mqtt` source with a broker address while `direct` is active
- **THEN** the S7 poller stops, the dashboard subscribes to the submitted broker, the previous values are cleared, and the connecting state shows until MQTT data arrives

#### Scenario: Switch from MQTT to direct at runtime
- **WHEN** the user requests the `direct` source while `mqtt` is active
- **THEN** the MQTT subscription stops, the dashboard connects to its own configured PLC over S7, the previous values are cleared, and the connecting state shows until PLC data arrives

#### Scenario: Switch to an unavailable source
- **WHEN** the user requests a source whose PLC or broker is unreachable
- **THEN** the previous values are cleared, a connecting state is shown, and the connection becomes stale after the applicable staleness behaviour, while the dashboard keeps retrying

#### Scenario: No phantom counts across a source switch
- **WHEN** the active signal (for example the green tower light P3) is already ON when a newly started source delivers its first snapshot
- **THEN** no cycle or metal-detection count is generated from that snapshot; counts resume only from a later rising edge

#### Scenario: Invalid source request rejected
- **WHEN** a source switch is requested for a source other than `direct` or `mqtt`
- **THEN** the request is rejected with an error and the active source is unchanged

### Requirement: Stats follow the active source
Per-minute statistics SHALL default to the active source's connection: the configured PLC's IP in `direct` mode, the submitted broker address in `mqtt` mode. Per-minute counts are kept in memory for the currently active connection only; when the active source or broker address changes, the counts SHALL reset and the charts SHALL start from an empty window for the newly connected target (no counts from the previous connection are shown).

#### Scenario: Charts follow a source switch
- **WHEN** the user switches from a MQTT broker back to `direct` (the configured PLC)
- **THEN** the per-minute charts start from an empty window for the configured PLC and fill only with newly counted events

#### Scenario: Stats request for a non-active connection
- **WHEN** a stats request names a connection other than the currently active one
- **THEN** the response reflects the active connection's counts (the request's filter has no effect)

### Requirement: MQTT liveness detection
In MQTT mode the dashboard SHALL judge liveness by packet cadence alone: the connection SHALL be marked stale when no new snapshot has arrived for a staleness timeout of approximately 1 second. There SHALL be no status topic, offline message, or Last Will involved in liveness. When fresh snapshots resume, the stale state SHALL clear automatically and the first snapshot after a stale period SHALL only re-baseline (no counts).

#### Scenario: Publisher goes offline
- **WHEN** the publisher process dies or disconnects from its broker
- **THEN** `plc_tags` packets stop arriving and the dashboard marks the connection stale within approximately 1 second

#### Scenario: Silent broker
- **WHEN** no snapshot has been received for approximately 1 second
- **THEN** the dashboard shows the stale state

#### Scenario: Recovery
- **WHEN** fresh snapshots resume after a stale period
- **THEN** the stale state clears, live values resume, and no count is generated from the first snapshot after the gap

## ADDED Requirements

### Requirement: Broker address selection
In `mqtt` mode the dashboard SHALL accept a broker address typed by the user, in the form `IP` or `IP:port` where a bare IP defaults to port 1883, and SHALL connect (or reconnect) the MQTT source to that address when it is submitted. Submitting a new address while already in `mqtt` mode SHALL behave like a source switch: displayed values are cleared, a "connecting…" state shows, and counting re-baselines (no counts credited across the change). The dashboard SHALL remember the last submitted address in browser localStorage, pre-fill the field with it, and auto-connect to it on page load. When `mqtt` is the startup source (`DATA_SOURCE=mqtt`) and no address has been submitted yet, the dashboard SHALL show the connecting state and operate no MQTT source until an address is submitted.

#### Scenario: Bare IP defaults to port 1883
- **WHEN** the user submits `192.168.0.11`
- **THEN** the dashboard connects to the broker at `192.168.0.11:1883`

#### Scenario: Explicit port accepted
- **WHEN** the user submits `192.168.0.11:1884`
- **THEN** the dashboard connects to the broker at `192.168.0.11:1884`

#### Scenario: Retyping an address while in MQTT mode
- **WHEN** the user submits a new broker address while the `mqtt` source is already active
- **THEN** the previous subscription stops, the displayed values are cleared, a connecting state shows until data arrives, and no counts from the previous broker remain

#### Scenario: Startup in MQTT mode without an address
- **WHEN** the dashboard starts with `DATA_SOURCE=mqtt` and the user has not submitted an address
- **THEN** no MQTT source is active and the UI shows the connecting state until an address is submitted

#### Scenario: Address remembered across page loads
- **WHEN** a broker address has been successfully submitted and the page is reloaded
- **THEN** the field is pre-filled with that address and the dashboard auto-connects to it

## REMOVED Requirements

### Requirement: Line registry and selection
**Reason**: The broker is now typed directly by the user, so the `.env` line registry and its dropdown are unnecessary.
**Migration**: Operators type the line's broker address (`IP` or `IP:port`) in the dashboard's MQTT input instead of selecting a registered line.

### Requirement: Line switching behaviour
**Reason**: Replaced by broker address selection (see `Broker address selection`); there are no registry lines to switch between.
**Migration**: Submitting a new broker address performs the same clear-connecting-rebaseline sequence the line switch used to provide.
