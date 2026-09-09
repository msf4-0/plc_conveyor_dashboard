# oee-monitoring Delta

## Purpose

Computes Overall Equipment Effectiveness (Availability × Performance × Quality) per the methodology at https://www.oee.com/calculating-oee/, from in-memory cycle counts and run/stop time accumulators driven by the line operating state, and displays the results in a dashboard panel with a user-editable Ideal Cycle Time.

## ADDED Requirements

### Requirement: OEE cycle counting at start sensor
The system SHALL increment the OEE Total Count each time the start sensor B3 (I0.5, PX1) transitions from FALSE to TRUE (rising edge) while the line state is READY or RUNNING. B3 rising edges while the line is NOT READY or STOPPED SHALL NOT open a cycle and SHALL NOT increment any count. Cycle start and cycle end (classification) SHALL both be considered only while the line is in READY or RUNNING. This OEE cycle definition is independent of the existing green-light (P3) cycle-completion counter, which SHALL remain unchanged.

#### Scenario: Part enters the line
- **WHEN** B3 transitions from FALSE to TRUE while the line is READY or RUNNING
- **THEN** the OEE Total Count increases by exactly one

#### Scenario: Edge ignored while stopped
- **WHEN** B3 produces a rising edge while the line state is NOT READY or STOPPED
- **THEN** no cycle is opened and no count changes

#### Scenario: Edge counted while merely ready
- **WHEN** B3 produces a rising edge while the line state is READY (motor not yet on)
- **THEN** the OEE Total Count increases by exactly one

#### Scenario: Green-light counter unaffected
- **WHEN** an OEE cycle is counted at B3
- **THEN** the existing P3-based per-minute cycle chart is unchanged by that event

### Requirement: Good/bad classification at finish sensor
Each OEE cycle opened by a B3 rising edge SHALL be classified when the part reaches the finish sensor B1 (I0.7, PX3) rising edge while the line state is READY or RUNNING: the cycle is a **good count** if and only if B2 (I0.6, PX2) and B1 were both triggered since the B3 edge and the metal detector B4 (I1.0) was NOT triggered since the B3 edge; otherwise it is a **bad count**. A cycle opened by B3 that has not yet been classified SHALL be reported as "In-flight" (displayed under Bad). Total Count SHALL equal Good Count plus Bad Count (with In-flight included in Bad). A B1 rising edge while the line is NOT READY or STOPPED SHALL NOT classify a cycle; a cycle opened while READY/RUNNING remains In-flight until it can be classified in READY/RUNNING.

#### Scenario: Clean part finishes
- **WHEN** a cycle's part triggers B3, then B2, then B1, with no B4 detection since the B3 edge, while the line is READY or RUNNING
- **THEN** the cycle is classified as a good count

#### Scenario: Metal detected during cycle
- **WHEN** B4 detects metal at any point between a cycle's B3 edge and its B1 edge
- **THEN** the cycle is classified as a bad count when B1 rises in READY or RUNNING

#### Scenario: Part misses the middle sensor
- **WHEN** a cycle's part triggers B3 and B1 but never B2 since the B3 edge
- **THEN** the cycle is classified as a bad count

#### Scenario: Cycle still in flight
- **WHEN** a cycle was opened by B3 but its part has not yet triggered B1
- **THEN** the cycle is counted as In-flight under Bad, and Total = Good + Bad including In-flight

#### Scenario: Classification deferred while stopped
- **WHEN** a part reaches B1 (B1 rises) while the line is STOPPED
- **THEN** the open cycle is not classified; it is classified later when B1 rises again during READY or RUNNING

### Requirement: Run and stop time accumulation
The system SHALL accumulate Run Time in memory from the moment the line enters the READY state, inclusive of STOPPED time, and SHALL accumulate Stop Time for the duration the line state is STOPPED. Timing SHALL be quantized by the polling interval (~500 ms). On dashboard startup with the line already running, the accumulator SHALL begin from the first post-baseline snapshot.

#### Scenario: Run time starts at ready
- **WHEN** the line state transitions from NOT READY to READY
- **THEN** Run Time accumulation begins from that moment

#### Scenario: Stop time accrues
- **WHEN** the line remains in the STOPPED state for a period
- **THEN** Stop Time increases by that period and Run Time continues to accumulate

#### Scenario: Ready again after stop
- **WHEN** the line returns from STOPPED to READY and then RUNNING
- **THEN** Run Time keeps accumulating from the original READY entry without reset

### Requirement: Pause on disconnect
While the dashboard is disconnected, stale, or pointed at another line, all OEE accumulators (Run Time, Stop Time) and cycle counting SHALL be paused. No time or counts SHALL be attributed to the disconnected period, and the first snapshot after reconnect SHALL re-baseline without producing counts.

#### Scenario: Disconnect pauses timers
- **WHEN** the PLC connection is lost for one minute while the line is RUNNING
- **THEN** neither Run Time nor Stop Time increases for that minute

#### Scenario: Reconnect re-baselines
- **WHEN** the connection is restored and the first snapshot arrives
- **THEN** no counts are generated from that snapshot and accumulation resumes

### Requirement: OEE calculation
The system SHALL compute, for the active accumulator:
- Availability = (Run Time − Stop Time) / Run Time
- Performance = (Ideal Cycle Time × Total Count) / Run Time
- Quality = Good Count / Total Count
- OEE = Availability × Performance × Quality

All four values SHALL be expressed as percentages. When Run Time is zero, Availability, Performance, and OEE SHALL be displayed as not available ("—") rather than dividing by zero.

#### Scenario: OEE from factors
- **WHEN** Availability, Performance, and Quality are computed
- **THEN** the dashboard shows OEE as their product, as a percentage

#### Scenario: No run time yet
- **WHEN** Run Time is zero (line never entered READY since startup or reset)
- **THEN** Availability, Performance, and OEE display "—" and no division by zero occurs

### Requirement: Ideal cycle time input and persistence
The dashboard SHALL provide a user-editable Ideal Cycle Time input for the Performance calculation, defaulting to 5 seconds, validated to the range 0.1–3600 seconds. The value SHALL be persisted server-side in PostgreSQL per line (`line_ip`), SHALL survive dashboard restarts, and a newly saved value SHALL take effect immediately. The PLC SHALL NOT be written to.

#### Scenario: Default value
- **WHEN** a line has no stored Ideal Cycle Time
- **THEN** the dashboard uses and displays 5 seconds

#### Scenario: User updates value
- **WHEN** the user enters a valid Ideal Cycle Time and saves it
- **THEN** the value is persisted for that line and Performance uses it immediately

#### Scenario: Invalid input rejected
- **WHEN** the user enters a value outside 0.1–3600 seconds
- **THEN** the input is rejected with a visible error and the previous value remains in effect

#### Scenario: Value survives restart
- **WHEN** the dashboard is restarted after saving an Ideal Cycle Time
- **THEN** the stored value for the selected line is loaded and used

### Requirement: OEE reset control
The dashboard SHALL provide a Reset control that zeroes all OEE accumulators — Total, Good, Bad, In-flight counts, Run Time, Stop Time, and derived metrics — without changing the line operating state. The Ideal Cycle Time value SHALL NOT be reset.

Pressing the panel reset button (S3, I0.3) SHALL trigger the same full OEE reset (zeroing all accumulators except the Ideal Cycle Time) and SHALL additionally force the line state machine to NOT READY (see the `line-operating-state` capability). S3 is the only reset that changes the line state; the dashboard's Reset control never does. As with all buttons, a momentary S3 press shorter than the polling interval (~500 ms) may not be observed.

#### Scenario: Reset zeroes metrics
- **WHEN** the user activates the OEE Reset control
- **THEN** all counts and times are zero, OEE displays "—", and the line state is unchanged

#### Scenario: Reset keeps ideal cycle time
- **WHEN** the OEE Reset control is activated
- **THEN** the Ideal Cycle Time value remains as previously set

#### Scenario: Panel reset zeroes OEE and enters NOT READY
- **WHEN** the panel reset button S3 is pressed while the line is READY, RUNNING, or STOPPED and OEE metrics are non-zero
- **THEN** all OEE counts and times are zeroed, OEE displays "—", and the line state becomes NOT READY

#### Scenario: Panel reset keeps ideal cycle time
- **WHEN** the panel reset button S3 is pressed
- **THEN** the Ideal Cycle Time value remains as previously set

#### Scenario: Panel reset does not affect per-minute counters
- **WHEN** the panel reset button S3 is pressed
- **THEN** the existing per-minute cycle and metal-detection counters and charts (the `production-statistics` capability) are unaffected

### Requirement: Line switch resets OEE
Switching the selected line (`line_ip`) SHALL perform a full OEE reset equivalent to the Reset control for the new line's accumulator, while retaining the new line's persisted Ideal Cycle Time.

#### Scenario: Switching lines
- **WHEN** the user selects a different line
- **THEN** the OEE panel shows zeroed metrics and the newly selected line's Ideal Cycle Time

### Requirement: OEE panel display
The dashboard SHALL display an OEE panel showing: Availability, Performance, Quality, and OEE percentages; Good, Bad (including the In-flight sub-count), and Total counts; and elapsed Run Time and Stop Time. The existing per-minute count charts SHALL remain unchanged.

#### Scenario: Panel shows metrics
- **WHEN** the dashboard is viewed
- **THEN** the OEE panel shows A, P, Q, and OEE percentages, Good/Bad (with In-flight)/Total counts, and Run/Stop time alongside the existing charts

### Requirement: In-memory OEE limitation
OEE accumulators are intentionally in-memory: a dashboard or server restart SHALL reset all OEE metrics to zero and the line state machine to NOT READY. This limitation SHALL be documented in the dashboard documentation.

#### Scenario: Restart clears OEE
- **WHEN** the dashboard process is restarted
- **THEN** all OEE metrics start at zero and the state machine starts in NOT READY, and this behavior is stated in the dashboard documentation
