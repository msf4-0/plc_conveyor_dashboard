from app.tags import TAGS, Area, Kind, button_pressed, raw_values


def test_tag_addresses_match_plc_tags_csv():
    expected = {
        "ESO": (Area.INPUT, 1, 1),
        "S1": (Area.INPUT, 0, 1),
        "S2": (Area.INPUT, 0, 2),
        "S3": (Area.INPUT, 0, 3),
        "B1": (Area.INPUT, 0, 7),
        "B2": (Area.INPUT, 0, 6),
        "B3": (Area.INPUT, 0, 5),
        "B4": (Area.INPUT, 1, 0),
        "K1": (Area.OUTPUT, 0, 3),
        "K2": (Area.OUTPUT, 0, 4),
        "K3": (Area.OUTPUT, 0, 5),
        "P1": (Area.OUTPUT, 1, 0),
        "P2": (Area.OUTPUT, 0, 7),
        "P3": (Area.OUTPUT, 0, 6),
    }
    assert set(TAGS) == set(expected)
    for name, (area, byte, bit) in expected.items():
        tag = TAGS[name]
        assert (tag.area, tag.byte, tag.bit) == (area, byte, bit), name


def test_button_polarity():
    assert TAGS["S1"].active_low and TAGS["ESO"].active_low
    assert not TAGS["S2"].active_low and not TAGS["S3"].active_low
    # NC buttons: pressed when input reads FALSE
    assert button_pressed(False, TAGS["S1"]) is True
    assert button_pressed(True, TAGS["S1"]) is False
    # NO buttons: pressed when input reads TRUE
    assert button_pressed(True, TAGS["S2"]) is True
    assert button_pressed(False, TAGS["S2"]) is False


def test_raw_values_extraction():
    inputs = bytes([0b00001010, 0b00000010])  # I0.1,I0.3 set; I1.1 set
    outputs = bytes([0b01000000, 0b00000001])  # Q0.6 set; Q1.0 set
    raw = raw_values(inputs, outputs)
    assert raw["S1"] is True and raw["S3"] is True and raw["S2"] is False
    assert raw["ESO"] is True
    assert raw["B3"] is False and raw["B4"] is False
    assert raw["P3"] is True and raw["P1"] is True and raw["P2"] is False
    assert raw["K1"] is False


def test_kinds():
    assert TAGS["B4"].kind is Kind.SENSOR
    assert TAGS["P3"].kind is Kind.LIGHT
    assert TAGS["K1"].kind is Kind.MOTOR
