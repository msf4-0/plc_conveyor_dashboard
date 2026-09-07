# plc-connectivity Delta

## ADDED Requirements

### Requirement: Runtime source switching
The dashboard SHALL allow switching the active data source between `direct` and `mqtt` at runtime without an application restart. `direct` SHALL always mean a read-only S7 connection to the dashboard's own configured PLC (`PLC_IP`/`PLC_RACK`/`PLC_SLOT`); direct connections to other lines' PLCs are out of scope. Switching sources SHALL stop the previous source, start the requested one from the existing configuration, clear the displayed values, show a "connecting…" state until the new source delivers data (or stale, if it cannot), and indicate the active source on the UI. The startup source SHALL remain the `DATA_SOURCE` configuration value.

#### Scenario: Switch from direct to MQTT at runtime
- **WHEN** the user requests the `mqtt` source while `direct` is active
- **THEN** the S7 poller stops, the dashboard subscribes to the configured MQTT broker/line, the previous values are cleared, and the connecting state shows until MQTT data arrives

#### Scenario: Switch from MQTT to direct at runtime
- **WHEN** the user requests the `direct` source while `mqtt` is active
- **THEN** the MQTT subscription stops, the dashboard connects to its own configured PLC over S7, the previous values are cleared, and the connecting state shows until PLC data arrives

#### Scenario: Switch to an unavailable source
- **WHEN** the user requests a source whose PLC or broker is unreachable
- **THEN** the previous values are cleared, a connecting state is shown, and the line becomes stale after the applicable staleness behaviour, while the dashboard keeps retrying

#### Scenario: No phantom counts across a source switch
- **WHEN** the active signal (for example the green tower light P3) is already ON when a newly started source delivers its first snapshot
- **THEN** no cycle or metal-detection count is generated from that snapshot; counts resume only from a later rising edge

#### Scenario: Invalid source request rejected
- **WHEN** a source switch is requested for a source other than `direct` or `mqtt`
- **THEN** the request is rejected with an error and the active source is unchanged

### Requirement: Stats follow the active source
Per-minute statistics SHALL default to the active source's line: the configured PLC's IP in `direct` mode, the selected line's PLC IP in `mqtt` mode. When the active source or line changes, the charts SHALL reflect the newly active line's counts.

#### Scenario: Charts follow a source switch
- **WHEN** the user switches from the MQTT line `10.0.0.2` back to `direct` (the configured PLC)
- **THEN** the per-minute charts show the configured PLC's counts only

## MODIFIED Requirements

### Requirement: Selectable data source
The dashboard SHALL support two data sources: `direct` (a direct read-only S7 connection to the configured PLC, behaving exactly as before this change) and `mqtt` (subscribing to the MQTT broker of the selected line). The startup source SHALL be selected by configuration (`DATA_SOURCE`), and the active source SHALL be switchable at runtime from the dashboard. The active source SHALL be indicated on the UI.

#### Scenario: Direct mode unchanged
- **WHEN** the data source is configured as `direct`
- **THEN** the dashboard polls the configured PLC over S7 as it did before this change

#### Scenario: MQTT mode subscribes to the selected line
- **WHEN** the data source is configured as `mqtt`
- **THEN** the dashboard subscribes to the selected line's broker and its displayed state derives from received MQTT snapshots

#### Scenario: Source shown on UI
- **WHEN** the dashboard is viewed
- **THEN** the UI indicates whether the current data source is direct or MQTT

#### Scenario: Source switchable at runtime
- **WHEN** the user requests the other source from the dashboard while it is running
- **THEN** the dashboard switches data sources without requiring an application restart
