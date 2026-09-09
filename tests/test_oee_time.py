"""Run/stop time accumulation and pause-on-disconnect scenarios
(specs/oee-recording: "Run and stop time accumulation", "Pause on disconnect").

Run Time accrues while connected from recorder start; Stop Time accrues
while the red tower light P1 is on. An interval is credited per the signals
that held during it.
"""

from app.oee import OeeEngine
from tests.oee_sim import feed


def times(engine):
    m = engine.metrics()
    return m["run_time_s"], m["stop_time_s"]


def approx(a, b, tol=0.01):
    return abs(a - b) <= tol


def test_run_time_accrues_from_startup():
    engine = OeeEngine()
    feed(engine, {}, {}, {}, start=0.0, step=2.0)  # connected, idle
    run, stop = times(engine)
    assert approx(run, 4.0)  # intervals t=0->2 and t=2->4
    assert stop == 0.0


def test_stop_time_accrues_while_red_light_on():
    engine = OeeEngine()
    # t=2: P1 off interval; t=4, t=6: P1 held intervals
    feed(engine, {}, {"P1": True}, {"P1": True}, {"P1": True},
         start=0.0, step=2.0)
    run, stop = times(engine)
    assert approx(run, 6.0)   # run keeps accruing while stopped
    assert approx(stop, 4.0)  # intervals t=2->4 and t=4->6 held P1


def test_run_time_continues_accumulating_after_stop_clears():
    engine = OeeEngine()
    feed(engine, {}, {"P1": True}, {"P1": True}, {"P1": False},
         start=0.0, step=2.0)
    run, stop = times(engine)
    assert approx(run, 6.0)
    assert approx(stop, 4.0)  # intervals t=2->4 and t=4->6 held P1


def test_stop_time_credited_per_held_interval():
    """A P1 that rises and falls between snapshots still credits the whole
    interval it was held in (quantized by the poll interval)."""
    engine = OeeEngine()
    feed(engine, {}, {"P1": True}, {"P1": False}, start=0.0, step=2.0)
    run, stop = times(engine)
    assert approx(run, 4.0)
    assert approx(stop, 2.0)  # interval t=2->4 held P1


def test_disconnect_pauses_accumulation():
    engine = OeeEngine()
    t = feed(engine, {}, {}, start=0.0, step=2.0)  # run = 2.0, t = 2
    engine.on_disconnect()
    # 100 s offline: must not be credited; reconnect snapshot re-baselines
    feed(engine, {"K1": True}, {"K1": True}, start=t + 100.0, step=2.0)
    run, stop = times(engine)
    assert approx(run, 4.0)  # pre-disconnect 2 s + one post-reconnect interval
    assert stop == 0.0


def test_no_phantom_counts_across_reconnect_baseline():
    engine = OeeEngine()
    t = feed(engine, {}, {"B3": True}, start=0.0, step=2.0)
    assert engine.metrics()["total"] == 1
    engine.on_disconnect()
    # B3 already on when data resumes: baseline only, no new cycle, no time
    feed(engine, {"B3": True}, start=t + 50.0, step=2.0)
    m = engine.metrics()
    assert m["total"] == 1
    assert approx(m["run_time_s"], 2.0)  # pre-disconnect time only; gap not credited


def test_stop_time_not_credited_across_reconnect_with_p1_high():
    engine = OeeEngine()
    t = feed(engine, {}, {"P1": True}, {"P1": True}, start=0.0, step=2.0)
    assert approx(times(engine)[1], 2.0)
    engine.on_disconnect()
    # P1 is already on when the connection resumes
    feed(engine, {"P1": True}, {"P1": True}, start=t + 30.0, step=2.0)
    run, stop = times(engine)
    assert approx(run, 6.0)   # pre-disconnect 4 s + one post-reconnect interval
    assert approx(stop, 4.0)  # the held-P1 interval after the baseline
