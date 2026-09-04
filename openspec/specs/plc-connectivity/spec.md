# plc-connectivity Specification

## Purpose

Establishes and maintains the read-only data link between the dashboard and the Siemens S7-1200 PLC over Ethernet, so that all other dashboard capabilities receive fresh, trustworthy process-image data and degrade safely when the link is lost.

## Requirements

### Requirement: S7 connection to the PLC
The system SHALL connect to the S7-1200 PLC over Ethernet using the S7 protocol (PUT/GET) and SHALL read the process image without writing to the PLC.

#### Scenario: Successful connection
- **WHEN** the dashboard starts and the PLC is reachable on the configured Ethernet address
- **THEN** the system establishes an S7 connection and begins reading the process image

#### Scenario: PLC unreachable at startup
- **WHEN** the dashboard starts and the PLC cannot be reached
- **THEN** the system retries the connection continuously and shows the disconnected state on the UI

### Requirement: Polling of the process image
The system SHALL poll the PLC inputs and outputs listed in `plc_tags.csv` (ESO, S1, S2, S3, B1, B2, B3, B4, K1, K2, K3, P1, P2, P3) at approximately 500 ms intervals.

#### Scenario: Fresh data at steady state
- **WHEN** the connection is established
- **THEN** process-image values are refreshed and made available to the UI at a rate of approximately 500 ms

### Requirement: Stale data handling on connection loss
The system SHALL freeze the last received values on screen and SHALL display a prominent "stale / connection lost" banner when the PLC connection is lost. The system SHALL resume live updates automatically when the connection is re-established.

#### Scenario: Connection lost during operation
- **WHEN** the PLC connection drops while the dashboard is running
- **THEN** the last received values remain displayed, a prominent stale/connection-lost banner is shown, and no values are updated from memory

#### Scenario: Automatic recovery
- **WHEN** the PLC becomes reachable again after a connection loss
- **THEN** the stale banner is removed and live updates resume without user intervention
