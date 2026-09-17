# mqtt-line-transport Specification (delta)

## ADDED Requirements

### Requirement: Broker authentication with a shared credential
The line-PC broker SHALL reject MQTT connections that do not present a username and password matching the single shared credential configured in `.env` (`MQTT_USERNAME`/`MQTT_PASSWORD`, required at startup, fail-fast). Any client presenting the shared credential SHALL be able to connect, publish, and subscribe. Publisher and dashboard MQTT subscriber SHALL send the shared credential when connecting. A dashboard pointed at a third-party broker that does not require authentication SHALL still work: such a broker ignores the credential.

#### Scenario: Authorized client connects
- **WHEN** the publisher or the dashboard connects to the line's broker presenting the shared username and password
- **THEN** the connection succeeds and `plc_tags` messages flow as before

#### Scenario: Anonymous or wrong-credential client is rejected
- **WHEN** a client attempts to connect to the broker without credentials, or with credentials that do not match the shared credential
- **THEN** the broker refuses the connection

#### Scenario: Missing MQTT credential configuration stops startup
- **WHEN** the broker, publisher, or dashboard is started without `MQTT_USERNAME` or `MQTT_PASSWORD` set
- **THEN** startup fails with an error naming the missing variable

### Requirement: Broker topic lock
The broker SHALL only accept publish and subscribe operations on the fixed topic `plc_tags`. Operations on any other topic SHALL be rejected or ignored, so the broker cannot be used as an open relay.

#### Scenario: plc_tags remains fully functional
- **WHEN** an authenticated client publishes to or subscribes on `plc_tags`
- **THEN** the operations succeed as before

#### Scenario: Other topics are not served
- **WHEN** an authenticated client attempts to publish or subscribe on a topic other than `plc_tags`
- **THEN** the broker rejects or silently drops the operation

## REMOVED Requirements

### Requirement: Broker without authentication
**Reason**: The broker previously accepted anonymous connections on `0.0.0.0`, which let any LAN client publish well-formed `plc_tags` payloads (injecting phantom counts into the dashboard) or subscribe to line data. The new shared-credential authentication replaces this requirement.
**Migration**: Start the broker, publisher, and dashboard with `MQTT_USERNAME`/`MQTT_PASSWORD` set in `.env`; every MQTT client sends the shared credential at connect time (`username`/`password` in the MQTT CONNECT packet).
