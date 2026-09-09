## Purpose

Records Overall Equipment Effectiveness (Availability × Performance × Quality) for the PLC connected directly to the PC, via a standalone recorder process that polls the PLC over snap7 and persists a history of OEE figures to the PC's local PostgreSQL database, independently of the dashboard.

## ADDED Requirements

### Requirement: Standalone recorder process
The system SHALL provide a standalone OEE recorder process that reads the directly-connected PLC's process image over snap7 (read-only) at the configured poll interval and persists OEE figures to the local `oee` PostgreSQL database. Recording SHALL start the moment the recorder process starts: no line operating state machine SHALL gate counting or timing, and no user action SHALL be required to begin. The recorder SHALL run independently of the dashboard process: starting, stopping, or using the dashboard SHALL NOT affect recording, and recording SHALL continue while the dashboard is not running.

#### Scenario: Recording starts immediately
- **WHEN** the recorder process starts and the PLC is connected
- **THEN** OEE figures are computed and persisted without any start button press or user action

#### Scenario: Independent of the dashboard
- **WHEN** the dashboard process is stopped or its data source is switched while the recorder is running
- **THEN** the recorder continues to poll the PLC and persist OEE rows unchanged

### Requirement: Ungated cycle counting
The recorder SHALL count production cycles from sensor rising edges regardless of any line state: each start-sensor B3 (I0.5) rising edge SHALL open one cycle; the cycle SHALL be classified when the finish-sensor B1 (I0.7) rising edge occurs — a good count if and only if the middle sensor B2 (I0.6) was triggered since the B3 edge and the metal detector B4 (I1.0) was NOT triggered since the B3 edge, otherwise a bad count. A cycle opened but not yet classified SHALL be reported as in-flight and included in the bad count (Total Count SHALL equal Good Count plus Bad Count including in-flight). A new B3 edge before the previous cycle reaches B1 SHALL force-classify the previous open cycle as a bad count.

#### Scenario: Clean part finishes
- **WHEN** a part triggers B3, then B2, then B1 with no B4 detection since the B3 edge
- **THEN** the cycle is classified as a good count

#### Scenario: Metal detected during cycle
- **WHEN** B4 detects metal at any point between a cycle's B3 edge and its B1 edge
- **THEN** the cycle is classified as a bad count when B1 rises

#### Scenario: Part misses the middle sensor
- **WHEN** a part triggers B3 and B1 but never B2 since the B3 edge
- **THEN** the cycle is classified as a bad count

#### Scenario: Part enters before previous finished
- **WHEN** B3 rises while a cycle is still open
- **THEN** the previous open cycle is classified as a bad count and the new cycle is opened

#### Scenario: Counting needs no start button
- **WHEN** B3 produces a rising edge while the start button S2 has never been pressed
- **THEN** the cycle is counted (no line state blocks it)

### Requirement: Run and stop time accumulation
The recorder SHALL accumulate Run Time from the moment recording starts while the PLC connection is up, and SHALL accumulate Stop Time while the red tower light P1 (Q1.0) is TRUE. Timing SHALL be quantized by the polling interval.

#### Scenario: Run time accrues from startup
- **WHEN** the recorder has been connected to the PLC for a period
- **THEN** Run Time equals that period minus any Stop Time accrued during it

#### Scenario: Red light accrues stop time
- **WHEN** P1 is TRUE for a period while connected
- **THEN** Stop Time increases by that period and Run Time continues to accumulate

### Requirement: Pause on disconnect
While the PLC connection is down, all accumulation (Run Time, Stop Time, cycle counting) SHALL pause: no time or counts SHALL be attributed to the disconnected period, and the first snapshot after reconnect SHALL only re-baseline edge detection without producing counts.

#### Scenario: Disconnect pauses timers
- **WHEN** the PLC connection is lost for one minute while the line is running
- **THEN** neither Run Time nor Stop Time increases for that minute

#### Scenario: Reconnect re-baselines
- **WHEN** the connection is restored and the first snapshot arrives
- **THEN** no counts are generated from that snapshot and accumulation resumes

### Requirement: OEE calculation
The recorder SHALL compute, from its accumulators:
- Availability = (Run Time − Stop Time) / Run Time
- Performance = (Ideal Cycle Time × Total Count) / Run Time
- Quality = Good Count / Total Count
- OEE = Availability × Performance × Quality

All four values SHALL be expressed as percentages. When Run Time is zero, the values SHALL be persisted as NULL (not available) rather than dividing by zero.

#### Scenario: OEE from factors
- **WHEN** Availability, Performance, and Quality are computed
- **THEN** OEE equals their product, as a percentage

#### Scenario: No run time yet
- **WHEN** Run Time is zero (recorder just started, line not yet accumulated time)
- **THEN** the persisted row contains NULL for the four figures

### Requirement: History persistence to the oee database
The recorder SHALL insert one row into table `oee` of the local `oee` PostgreSQL database every configured write interval, with columns `{timestamp, availability, performance, quality, oee}` where `timestamp` is the wall-clock time (UTC) of the snapshot. The table SHALL be created if absent. A failed database insert SHALL be logged and SHALL NOT stop the recorder: polling, counting, and subsequent inserts SHALL continue. The recorder SHALL NOT write to any other table or database, and SHALL NOT write to the PLC.

#### Scenario: Rows land at the write interval
- **WHEN** the recorder has been running with a 1-second write interval for one minute
- **THEN** approximately 60 rows have been inserted with increasing UTC timestamps

#### Scenario: Database outage does not stop recording
- **WHEN** the `oee` database is unreachable for a period and then recovers
- **THEN** the recorder keeps running, and inserts resume after recovery (rows for the outage are lost)

### Requirement: Recorder configuration via environment
The recorder SHALL be configured from environment variables (`.env`), failing fast at startup if required values are missing or invalid:
- `OEE_DATABASE_URL`: DSN of the local `oee` PostgreSQL database (required)
- `OEE_WRITE_INTERVAL_S`: seconds between persisted rows, default 1 (required to be positive)
- `IDEAL_CYCLE_TIME_S`: Ideal Cycle Time in seconds for the Performance calculation, default 5, validated to 0.1–3600
- `PLC_IP`, `PLC_RACK`, `PLC_SLOT`, `POLL_INTERVAL_MS`: PLC connection and poll interval (shared with the dashboard's direct mode)

The recorder SHALL NOT require the dashboard's own environment variables (`DATABASE_URL`, `HOST`, `PORT`).

#### Scenario: Missing database URL fails fast
- **WHEN** the recorder is started without `OEE_DATABASE_URL`
- **THEN** the process exits immediately with an explanatory error

#### Scenario: Invalid ideal cycle time rejected
- **WHEN** `IDEAL_CYCLE_TIME_S` is outside 0.1–3600
- **THEN** the recorder exits immediately with an explanatory error
