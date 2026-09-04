from app.edges import detect_events


def raw(**overrides):
    base = {t: False for t in ["P3", "B4", "B1", "B2", "B3", "K1"]}
    base.update(overrides)
    return base


def test_first_poll_baselines_without_events():
    assert detect_events(None, raw(P3=True, B4=True)) == []


def test_p3_rising_edge_counts_one_cycle():
    prev = raw(P3=False)
    cur = raw(P3=True)
    assert detect_events(prev, cur) == ["cycle_complete"]


def test_p3_stays_on_no_duplicate():
    prev = raw(P3=True)
    cur = raw(P3=True)
    assert detect_events(prev, cur) == []


def test_p3_falling_then_rising_counts_again():
    prev = raw(P3=True)
    mid = raw(P3=False)
    nxt = raw(P3=True)
    assert detect_events(prev, mid) == []
    assert detect_events(mid, nxt) == ["cycle_complete"]


def test_b4_rising_edge_counts_metal():
    prev = raw(B4=False)
    cur = raw(B4=True)
    assert detect_events(prev, cur) == ["metal_detected"]


def test_b4_sustained_only_one_event():
    prev = raw(B4=True)
    cur = raw(B4=True)
    assert detect_events(prev, cur) == []


def test_both_edges_same_poll():
    prev = raw(P3=False, B4=False)
    cur = raw(P3=True, B4=True)
    assert sorted(detect_events(prev, cur)) == ["cycle_complete", "metal_detected"]


def test_no_edges_when_quiet():
    prev = raw()
    cur = raw()
    assert detect_events(prev, cur) == []
