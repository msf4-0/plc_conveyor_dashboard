# line-operating-state Delta

## Purpose

Defines a formal four-state operating state machine for the conveyor line (NOT READY, READY, RUNNING, STOPPED), derived from the start push button, the reset push button, the motor relay, and the red tower light, and displays the current state as a badge at the top of the dashboard.

## ADDED Requirements

### Requirement: Line operating state machine
The system SHALL classify the line into exactly one of four states:
- **NOT READY**: the state after dashboard startup, before the start button (S2, I0.2) has been pressed; also re-entered whenever the panel reset button (S3, I0.3) is pressed.
- **READY**: entered when the start button S2 is pressed (rising edge of the effective press state).
- **RUNNING**: while in READY, when the motor relay K1 (Q0.3) is TRUE.
- **STOPPED**: while in READY, when the red tower light P1 (Q1.0) is TRUE. STOPPED SHALL take priority over RUNNING when both K1 is TRUE and P1 is TRUE. From STOPPED, the line SHALL return to READY only when the start button S2 is pressed again, or to NOT READY when the panel reset button S3 is pressed; the red tower light turning off alone SHALL NOT change the state.

A rising edge of the panel reset button S3 (effective press state; S3 is normally-open) SHALL force the line state to NOT READY from READY, RUNNING, or STOPPED, regardless of K1 or P1. If S3 and S2 rising edges are observed in the same poll snapshot, the reset SHALL take precedence (the state becomes NOT READY, not READY). State transitions SHALL be evaluated on every poll cycle of the process image.

#### Scenario: Startup before start button
- **WHEN** the dashboard starts and the start button S2 has not been pressed
- **THEN** the line state is NOT READY

#### Scenario: Start button pressed
- **WHEN** the start button S2 produces a rising edge while in NOT READY
- **THEN** the line state becomes READY

#### Scenario: Motor starts
- **WHEN** K1 becomes TRUE while in READY
- **THEN** the line state becomes RUNNING

#### Scenario: Red light stops the line
- **WHEN** P1 becomes TRUE while in READY or RUNNING
- **THEN** the line state becomes STOPPED, regardless of K1

#### Scenario: Red light clears without start button
- **WHEN** P1 returns to FALSE while in STOPPED and S2 is not pressed
- **THEN** the line state remains STOPPED

#### Scenario: Start button leaves STOPPED
- **WHEN** the start button S2 produces a rising edge while in STOPPED
- **THEN** the line state becomes READY

#### Scenario: Reset button returns a running line to NOT READY
- **WHEN** the panel reset button S3 produces a rising edge while in READY or RUNNING
- **THEN** the line state becomes NOT READY, and the line stays NOT READY until S2 is pressed again

#### Scenario: Reset button clears a stop
- **WHEN** the panel reset button S3 produces a rising edge while in STOPPED
- **THEN** the line state becomes NOT READY, regardless of the red tower light

#### Scenario: Reset button while already NOT READY
- **WHEN** the panel reset button S3 produces a rising edge while in NOT READY
- **THEN** the line state remains NOT READY

#### Scenario: Reset takes precedence over start in the same snapshot
- **WHEN** S2 and S3 rising edges are both observed in the same poll snapshot
- **THEN** the line state becomes NOT READY (reset wins), not READY

### Requirement: Re-baseline of state on (re)connect
The first snapshot after the dashboard (re)connects, after a line switch, or after a stale period SHALL be used only to establish the state baseline: the state SHALL be derived from that snapshot without generating false transitions, and no time SHALL be accumulated for the disconnected period.

#### Scenario: Reconnect with red light on
- **WHEN** the dashboard reconnects while P1 is already TRUE
- **THEN** the state is set to STOPPED from that snapshot without counting the disconnected duration as stop time

### Requirement: Disconnected state display
While the dashboard is disconnected or stale from the PLC/MQTT source, the state badge SHALL hold the last known state value and the OEE accumulator SHALL pause (see the `oee-monitoring` capability).

#### Scenario: Disconnect holds last state
- **WHEN** the connection to the PLC is lost while the state is RUNNING
- **THEN** the badge continues to show RUNNING until the connection is restored

### Requirement: Line state badge display
The dashboard SHALL display the current line state (NOT READY, READY, RUNNING, or STOPPED) as a badge at the top of the dashboard, updated on each poll cycle.

#### Scenario: Badge reflects current state
- **WHEN** the line state machine enters a new state
- **THEN** the badge at the top of the dashboard shows that state's name
