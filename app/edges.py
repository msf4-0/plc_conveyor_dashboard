from app.tags import EVENT_EDGES


def detect_events(previous: dict[str, bool] | None, current: dict[str, bool]) -> list[str]:
    """Return events for rising edges between two raw snapshots.

    previous=None means first poll after (re)connect: baseline only, no events,
    which prevents phantom counts after restarts or reconnects.
    """
    if previous is None:
        return []
    return [
        event
        for tag, event in EVENT_EDGES.items()
        if not previous.get(tag, False) and current.get(tag, False)
    ]
