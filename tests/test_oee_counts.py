"""OEE cycle counting and good/bad classification scenarios
(specs/oee-recording: "Ungated cycle counting" — no line state gating)."""

from app.oee import OeeEngine
from tests.oee_sim import feed


def counts(engine):
    m = engine.metrics()
    return {k: m[k] for k in ("total", "good", "bad", "in_flight")}


def test_part_entering_counts_one_cycle():
    engine = OeeEngine()
    feed(engine, {}, {"B3": True})
    assert counts(engine) == {"total": 1, "good": 0, "bad": 1, "in_flight": 1}


def test_clean_part_is_good():
    engine = OeeEngine()
    feed(engine, {},
         {"B3": True},
         {"B3": True, "B2": True},
         {"B2": True, "B1": True})
    assert counts(engine) == {"total": 1, "good": 1, "bad": 0, "in_flight": 0}


def test_metal_detection_makes_cycle_bad():
    engine = OeeEngine()
    feed(engine, {},
         {"B3": True},
         {"B3": True, "B4": True},            # metal flagged mid-cycle
         {"B3": True, "B4": True, "B2": True},
         {"B2": True, "B1": True})            # reaches B1: classified bad
    assert counts(engine) == {"total": 1, "good": 0, "bad": 1, "in_flight": 0}


def test_part_missing_middle_sensor_is_bad():
    engine = OeeEngine()
    feed(engine, {},
         {"B3": True},
         {"B3": True, "B1": True})            # B2 never triggered
    assert counts(engine) == {"total": 1, "good": 0, "bad": 1, "in_flight": 0}


def test_unclassified_cycle_shown_as_in_flight_under_bad():
    engine = OeeEngine()
    feed(engine, {},
         {"B3": True},
         {"B3": True, "B2": True})            # opened, not yet at B1
    c = counts(engine)
    assert c["in_flight"] == 1
    assert c["bad"] == 1                      # includes the in-flight part
    assert c["good"] == 0
    assert c["total"] == 1


def test_new_part_while_cycle_open_force_classifies_old_bad():
    engine = OeeEngine()
    feed(engine, {},
         {"B3": True},                        # cycle 1 opens
         {"B3": False},                       # part 1 never reaches B1
         {"B3": True})                        # cycle 2 opens: cycle 1 -> bad
    c = counts(engine)
    assert c["total"] == 2
    assert c["in_flight"] == 1                # cycle 2 still open
    assert c["bad"] == 2                      # 1 force-classified + 1 in-flight
    assert c["good"] == 0


def test_counting_needs_no_start_button():
    """Recording starts the moment the recorder starts: no gating state."""
    engine = OeeEngine()
    feed(engine, {}, {"B3": True})
    assert counts(engine)["total"] == 1


def test_cycles_counted_while_red_light_on():
    """No state machine: P1 (red light) does not block counting."""
    engine = OeeEngine()
    feed(engine, {},
         {"P1": True},
         {"P1": True, "B3": True},
         {"P1": True, "B3": False, "B1": True})
    c = counts(engine)
    assert c["total"] == 1
    assert c["bad"] == 1                      # B2 never triggered
    assert c["in_flight"] == 0


def test_classification_deferred_while_b1_stays_high():
    """A cycle opened at B3 classifies on the next B1 rising edge, even if
    B1 was already high when the cycle was still open."""
    engine = OeeEngine()
    feed(engine, {},
         {"B3": True, "B1": True},            # cycle opens; B1 high: classify now
         {"B3": False, "B1": False},          # part leaves
         {"B1": True})                        # B1 rising with no open cycle: ignored
    c = counts(engine)
    assert c["total"] == 1
    assert c["good"] + c["bad"] == 1
    assert c["in_flight"] == 0


def test_green_light_edge_does_not_affect_oee_counts():
    engine = OeeEngine()
    feed(engine, {},
         {"B3": True},
         {"B3": True, "B2": True, "B1": True, "P3": True})  # P3 rises too
    assert counts(engine) == {"total": 1, "good": 1, "bad": 0, "in_flight": 0}


def test_b1_rising_without_open_cycle_is_ignored():
    engine = OeeEngine()
    feed(engine, {}, {"B1": True})
    assert counts(engine) == {"total": 0, "good": 0, "bad": 0, "in_flight": 0}
