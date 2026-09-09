# mqtt-line-transport Specification

## Purpose

Publishes the conveyor line's PLC tag booleans over MQTT from the PC next to each conveyor line, so that a central dashboard can subscribe to any line's broker, receive fresh label-keyed snapshots on the single fixed `plc_tags` topic, and judge liveness purely from packet cadence.

## Requirements

### Requirement: Publisher reads the process image and publishes snapshots
The line-PC publisher SHALL connect to its S7-1200 PLC read-only (PUT/GET, no writes), read the process image at the configured poll interval (~500 ms), and publish a snapshot message to the fixed topic `plc_tags` after each successful read. If the PLC read fails, the publisher SHALL NOT publish a snapshot for that cycle and SHALL retry on subsequent cycles.

#### Scenario: Snapshot published at cadence
- **WHEN** the publisher is connected to both the PLC and the broker
- **THEN** a snapshot message is published to `plc_tags` approximately every poll interval (at least one packet per second)

#### Scenario: PLC read failure does not publish
- **WHEN** the PLC is unreachable or a read fails
- **THEN** no snapshot is published for that cycle and the publisher retries without crashing

#### Scenario: PLC access stays read-only
- **WHEN** the publisher communicates with the PLC
- **THEN** it only reads the process image and never writes any value to the PLC

### Requirement: Snapshot payload format
Each snapshot SHALL be a JSON object whose keys are exactly the 14 labels from `plc_tags.csv` (ESO, S1, S2, S3, B1, B2, B3, B4, K1, K2, K3, P1, P2, P3) and whose values are the booleans decoded from the snap7 process image at read time. The publisher SHALL NOT include a timestamp, PLC identity, or any other key; tag polarity remains the dashboard's responsibility.

#### Scenario: Payload decodes to the process image
- **WHEN** the dashboard reads a `plc_tags` payload
- **THEN** each label resolves to the same boolean value the publisher read from the PLC

#### Scenario: Payload carries only tag booleans
- **WHEN** a snapshot is inspected
- **THEN** it contains no timestamp, PLC IP, or metadata keys — only the 14 label keys with boolean values

#### Scenario: Payload identifies the line and read time
- **WHEN** a `plc_tags` snapshot is received
- **THEN** it carries no `plc_ip` line identity and no `ts` read time; the monitored line is determined solely by which broker address the dashboard connects to

### Requirement: Topic layout
The publisher SHALL publish snapshots to the single fixed topic `plc_tags`. The publisher SHALL NOT publish any status or liveness topic; the broker serves one line PC, and the dashboard's target line is chosen solely by which broker address it connects to.

#### Scenario: Topics are line-scoped
- **WHEN** multiple line PCs each run their own broker and publisher
- **THEN** each publisher emits snapshots only on its broker's single `plc_tags` topic; a dashboard watches exactly one line by connecting to one broker at a time, and no status topics exist

### Requirement: Broker without authentication
The line-PC broker SHALL accept MQTT connections without a username or password on its configured TCP port (default 1883) and SHALL deliver QoS 0 and QoS 1 messages, retained messages, and Last Will and Testament messages.

#### Scenario: Anonymous client connects
- **WHEN** the dashboard connects to a line's broker without credentials
- **THEN** the connection succeeds and subscriptions receive published messages

### Requirement: Local Python broker
The broker SHALL run as a pure-Python component installed in the project virtual environment, started by its own entrypoint on the line PC, and SHALL log connection and disconnection events.

#### Scenario: Broker starts on the line PC
- **WHEN** the broker entrypoint is started with its configured port
- **THEN** it accepts MQTT client connections and runs until stopped
