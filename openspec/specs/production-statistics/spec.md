# production-statistics Specification

## Purpose

Counts conveyor cycle completions and metal-detector detections from the process image, persists the counts to a local PostgreSQL server, and visualizes them as per-minute bar charts over a rolling 10-minute window.

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

### Requirement: Counter persistence in PostgreSQL
The system SHALL persist cycle-completion and metal-detection events with timestamps to the PostgreSQL server at `localhost:5432` (user `postgres`, password `postgres`) in appropriately named tables, so counts survive dashboard restarts.

#### Scenario: Event persisted
- **WHEN** a cycle completion or metal detection is counted
- **THEN** a timestamped event row is written to the corresponding PostgreSQL table

#### Scenario: Counts survive restart
- **WHEN** the dashboard is restarted after events have been recorded
- **THEN** previously persisted counts remain available and are not reset by the dashboard

### Requirement: Dashboard independence from panel Reset
The panel's Reset button (S3) is a PLC control only: it SHALL NOT reset or otherwise affect the dashboard's cycle or metal-detection counters.

#### Scenario: Reset button pressed
- **WHEN** the panel Reset button (S3) is pressed
- **THEN** the dashboard's counters are unchanged

### Requirement: Per-minute statistics charts
The system SHALL display bar charts of counts per minute over a rolling 10-minute window for both the cycle-completion counter and the metal-detection counter.

#### Scenario: Chart shows window
- **WHEN** the dashboard is viewed
- **THEN** each counter is shown as a bar chart of per-minute counts covering the last 10 minutes

#### Scenario: Window rolls forward
- **WHEN** time advances past the current 10-minute window
- **THEN** the charts drop the oldest minute and include the newest minute
