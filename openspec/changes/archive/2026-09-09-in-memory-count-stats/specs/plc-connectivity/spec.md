# plc-connectivity delta

## MODIFIED Requirements

### Requirement: Stats follow the active source
Per-minute statistics SHALL default to the active source's connection: the configured PLC's IP in `direct` mode, the selected line's PLC IP in `mqtt` mode. Per-minute counts are kept in memory for the currently active connection only; when the active source or line changes, the counts SHALL reset and the charts SHALL start from an empty window for the newly connected line (no counts from the previous connection or from other lines are shown).

#### Scenario: Charts follow a source switch
- **WHEN** the user switches from the MQTT line `10.0.0.2` back to `direct` (the configured PLC)
- **THEN** the per-minute charts start from an empty window for the configured PLC and fill only with newly counted events

#### Scenario: Stats request for a non-active line
- **WHEN** a stats request names a line other than the currently connected one
- **THEN** the response reflects the active connection's counts (the request's line filter has no effect)
