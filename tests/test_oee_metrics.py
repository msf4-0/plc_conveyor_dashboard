"""OEE metric computation scenarios (specs/oee-recording: "OEE calculation")."""

import pytest

from app.oee import OeeEngine
from tests.oee_sim import feed


def approx(a, b, tol=0.01):
    return abs(a - b) <= tol


def run_one_good_cycle(ideal=5.0):
    """One good cycle over six 2 s intervals of run time."""
    engine = OeeEngine(ideal_cycle_time_s=ideal)
    feed(engine, {},
         {"B3": True},                 # t=2: total=1
         {"B3": True, "B2": True},     # t=4
         {"B2": True, "B1": True},     # t=6: good=1
         start=0.0, step=2.0)
    return engine


def test_oee_equals_product_of_factors_for_clean_run():
    engine = run_one_good_cycle()
    m = engine.metrics()
    # run = 6 s (all intervals count), total=1, good=1, ideal=5
    assert approx(m["run_time_s"], 6.0)
    assert approx(m["availability"], 100.0)
    assert approx(m["performance"], 83.33)    # 5 s * 1 / 6 s
    assert approx(m["quality"], 100.0)
    assert approx(m["oee"], 83.33)


def test_availability_reflects_stop_time():
    engine = OeeEngine()
    # 2 s connected with P1 off, then 2 s with P1 on
    feed(engine, {}, {"P1": True}, {"P1": True}, start=0.0, step=2.0)
    m = engine.metrics()
    assert approx(m["run_time_s"], 4.0)
    assert approx(m["stop_time_s"], 2.0)
    assert approx(m["availability"], 50.0)    # (4 - 2) / 4


def test_quality_reflects_bad_counts():
    engine = OeeEngine()
    feed(engine, {},
         {"B3": True},                          # cycle 1
         {"B3": True, "B4": True},              # metal: cycle 1 doomed
         {"B4": True, "B3": False},             # part 1 exits, flagged bad later
         {"B3": True, "B4": True},              # cycle 1 -> bad, cycle 2 opens
         {"B4": True, "B2": True, "B1": True})  # cycle 2 -> bad
    m = engine.metrics()
    assert m["good"] == 0 and m["bad"] == 2
    assert m["quality"] == 0.0
    # OEE = A * P * 0 = 0
    assert m["oee"] == 0.0


def test_metrics_unavailable_before_run_time():
    engine = OeeEngine()
    feed(engine, {}, start=0.0, step=1.0)  # baseline only: run = 0
    m = engine.metrics()
    assert m["run_time_s"] == 0.0
    assert m["availability"] is None
    assert m["performance"] is None
    assert m["quality"] is None
    assert m["oee"] is None


def test_quality_unavailable_with_zero_total_but_time_elapsed():
    engine = OeeEngine()
    feed(engine, {}, {}, start=0.0, step=2.0)
    m = engine.metrics()
    assert m["run_time_s"] > 0
    assert m["availability"] is not None
    assert m["performance"] is not None   # ideal * 0 / run = 0
    assert m["quality"] is None
    assert m["oee"] is None


def test_performance_can_exceed_100_percent():
    engine = run_one_good_cycle(ideal=10.0)
    m = engine.metrics()
    assert m["performance"] > 100.0  # 10 s ideal vs 6 s actual
    assert m["oee"] > 100.0


def test_metrics_shape_has_no_state_machine_fields():
    engine = run_one_good_cycle()
    m = engine.metrics()
    assert set(m) == {
        "total", "good", "bad", "in_flight",
        "run_time_s", "stop_time_s", "ideal_cycle_time_s",
        "availability", "performance", "quality", "oee",
    }


def test_constructor_validates_ideal_cycle_time():
    assert OeeEngine(ideal_cycle_time_s=2.5).metrics()["ideal_cycle_time_s"] == 2.5
    for bad in (0.05, 3600.1, -1):
        with pytest.raises(ValueError):
            OeeEngine(ideal_cycle_time_s=bad)
