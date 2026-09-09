"""Shared snapshot-feeding helpers for OEE engine tests."""

from app.tags import TAGS


def raw(**overrides) -> dict[str, bool]:
    """A full process-image snapshot with all tags off unless overridden."""
    values = {name: False for name in TAGS}
    values.update(overrides)
    return values


def feed(engine, *states, start=0.0, step=1.0) -> float:
    """Feed snapshots `step` seconds apart starting at `start`.

    Each state is a partial dict merged onto the all-off base. The first
    snapshot only re-baselines. Returns the timestamp of the last snapshot.
    """
    t = start
    for state in states:
        engine.on_snapshot(raw(**state), t)
        t += step
    return t - step
