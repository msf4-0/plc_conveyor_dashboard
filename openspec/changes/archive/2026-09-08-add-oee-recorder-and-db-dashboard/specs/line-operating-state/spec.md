## REMOVED Requirements

### Requirement: Line operating state machine
**Reason**: The line operating state machine is deleted. OEE recording no longer uses line state (see the `oee-recording` capability), and the dashboard no longer derives or displays a line operating state; the start/reset button edge tracking it required is gone from the codebase.
**Migration**: None — the dashboard simply no longer shows a line state badge. Tower lights, conveyor motion, buttons, and sensors remain visible via their existing displays.

### Requirement: Re-baseline of state on (re)connect
**Reason**: No state machine exists to re-baseline. Edge detection re-baselining on (re)connect is preserved where counting still occurs (the recorder).
**Migration**: See the `oee-recording` capability's pause-on-disconnect requirement.

### Requirement: Disconnected state display
**Reason**: There is no state badge to hold; the stale banner and frozen-value behavior already cover disconnect presentation.
**Migration**: None — the existing stale banner continues to indicate connection loss.

### Requirement: Line state badge display
**Reason**: The badge is removed from the dashboard UI together with the state machine.
**Migration**: None.
