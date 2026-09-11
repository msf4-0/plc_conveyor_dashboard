from dataclasses import dataclass
from enum import Enum


class Area(str, Enum):
    INPUT = "I"
    OUTPUT = "Q"


@dataclass(frozen=True)
class Tag:
    name: str
    area: Area
    byte: int
    bit: int
    description: str
    # Normally-closed contacts read FALSE when pressed (Stop, E-stop).
    active_low: bool = False


# Derived from plc_tags.csv; polarity per design D7.
# ESO is assumed normally-closed (verify at commissioning - task 6.2).
TAGS: dict[str, Tag] = {
    tag.name: tag
    for tag in [
        Tag("ESO", Area.INPUT, 1, 1, "Emergency Stop", active_low=True),
        Tag("S1", Area.INPUT, 0, 1, "Stop push button", active_low=True),
        Tag("S2", Area.INPUT, 0, 2, "Start push button (G)"),
        Tag("S3", Area.INPUT, 0, 3, "Reset push button (Y)"),
        Tag("B1", Area.INPUT, 0, 7, "Finish sensor"),
        Tag("B2", Area.INPUT, 0, 6, "Middle sensor"),
        Tag("B3", Area.INPUT, 0, 5, "Start sensor"),
        Tag("B4", Area.INPUT, 1, 0, "Inductive sensor (metal detector)"),
        Tag("K1", Area.OUTPUT, 0, 3, "Relay for Motor"),
        Tag("K2", Area.OUTPUT, 0, 4, "Relay for direction"),
        Tag("K3", Area.OUTPUT, 0, 5, "Relay for speed"),
        Tag("P1", Area.OUTPUT, 1, 0, "Red Tower Light"),
        Tag("P2", Area.OUTPUT, 0, 7, "Yellow Tower Light"),
        Tag("P3", Area.OUTPUT, 0, 6, "Green Tower Light"),
    ]
}

# Cycle completion = green tower light rising edge; metal detection = B4 rising edge.
EVENT_EDGES = {"P3": "cycle_complete", "B4": "metal_detected"}


def read_bit(data: bytes | bytearray, tag: Tag) -> bool:
    """Extract a tag's boolean value from an area dump (2 bytes: byte0, byte1)."""
    return bool((data[tag.byte] >> tag.bit) & 1)


def raw_values(inputs: bytes | bytearray, outputs: bytes | bytearray) -> dict[str, bool]:
    values = {}
    for name, tag in TAGS.items():
        data = inputs if tag.area is Area.INPUT else outputs
        values[name] = read_bit(data, tag)
    return values


def button_pressed(tag_value: bool, tag: Tag) -> bool:
    return not tag_value if tag.active_low else tag_value
