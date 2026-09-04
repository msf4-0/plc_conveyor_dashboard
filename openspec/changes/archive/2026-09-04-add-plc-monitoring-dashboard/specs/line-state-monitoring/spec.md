## Purpose

Presents the live state of the manufacturing line — tower lights, push buttons, conveyor motion, and sensor detections — as at-a-glance visual indicators on a browser dashboard, mirroring the PLC process image.

## ADDED Requirements

### Requirement: Tower light display
The system SHALL display the state of the three tower lights as LED-style indicators: Red (P1, Q1.0), Yellow (P2, Q0.7), and Green (P3, Q0.6). Each indicator SHALL be rendered as a circular LED that glows in its own colour when its corresponding PLC output is TRUE, and appears dim/unlit when the output is FALSE.

#### Scenario: Light reflects PLC output
- **WHEN** a tower light output (P1, P2, or P3) is TRUE in the process image
- **THEN** the corresponding LED on the dashboard glows in that light's colour

#### Scenario: Light off
- **WHEN** a tower light output (P1, P2, or P3) is FALSE in the process image
- **THEN** the corresponding LED appears dim/unlit, without the colour glow

#### Scenario: Green light during cycle completion
- **WHEN** the cycle definition turns the green tower light (P3) on
- **THEN** the green LED on the dashboard glows green

### Requirement: Push button display
The system SHALL display the press state of the four panel buttons: Emergency Stop (ESO, I1.1), Stop (S1, I0.1), Start (S2, I0.2), and Reset (S3, I0.3). The Stop button and Emergency Stop are normally closed: a pressed state SHALL be displayed when the input reads FALSE (LOW). The Start and Reset buttons are normally open: a pressed state SHALL be displayed when the input reads TRUE (HIGH).

Each button SHALL be displayed as a pill badge containing its status text: the badge SHALL read "RELEASED" in grey while not pressed, and SHALL read "PRESSED" lit up in colour while pressed — red for Emergency Stop and Stop, yellow for Reset, and green for Start. The button label text SHALL also be rendered in that button's colour (red Emergency Stop and Stop, yellow Reset, green Start).

#### Scenario: Normally-open button pressed
- **WHEN** the Start button (S2) or Reset button (S3) is pressed so its input reads TRUE
- **THEN** the dashboard shows that button as pressed while the input remains TRUE

#### Scenario: Normally-closed button pressed
- **WHEN** the Stop button (S1) or Emergency Stop (ESO) is pressed so its input reads FALSE
- **THEN** the dashboard shows that button as pressed while the input remains FALSE

#### Scenario: Button badge styling
- **WHEN** a button is not pressed
- **THEN** its badge reads "RELEASED" in grey; when the button is pressed, its badge reads "PRESSED" lit up in the button's colour (red Emergency Stop and Stop, yellow Reset, green Start), matching the coloured label text

### Requirement: Conveyor motion display
The system SHALL display the conveyor belt motion as Running when the motor relay K1 (Q0.3) is TRUE and Stopped when K1 is FALSE. Direction and speed (K2, K3) SHALL NOT be displayed.

#### Scenario: Conveyor running
- **WHEN** the motor relay K1 is TRUE
- **THEN** the dashboard shows the conveyor as Running

#### Scenario: Conveyor stopped
- **WHEN** the motor relay K1 is FALSE
- **THEN** the dashboard shows the conveyor as Stopped

### Requirement: Sensor detection display
The system SHALL display the detection state of the three proximity sensors — Finish (B1, I0.7), Middle (B2, I0.6), Start (B3, I0.5) — and the metal detector (B4, I1.0), showing detected when the input is TRUE and clear when FALSE. Each sensor SHALL be displayed as a pill badge; the metal detector's badge text SHALL light up red while the metal detector is detecting, while the proximity sensor badges retain the neutral on/off styling.

#### Scenario: Sensor detects an object
- **WHEN** a sensor input (B1, B2, B3, or B4) reads TRUE
- **THEN** the dashboard shows that sensor as detecting

#### Scenario: Metal detector lights up red
- **WHEN** the metal detector B4 reads TRUE
- **THEN** the metal detector's badge text is lit up red; when B4 returns to FALSE, the badge returns to its neutral styling

#### Scenario: Sensor clears
- **WHEN** a sensor input that was TRUE returns to FALSE
- **THEN** the dashboard shows that sensor as clear

### Requirement: Momentary press limitation
The system SHALL document that momentary button presses shorter than the polling interval (~500 ms) may not be reflected on the dashboard.

#### Scenario: Press shorter than poll interval
- **WHEN** a button is pressed and released within a single polling interval
- **THEN** the press may not appear on the dashboard, and this limitation is stated in the dashboard documentation
