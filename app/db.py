from psycopg import Connection, connect

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS line_events (
    id          BIGSERIAL PRIMARY KEY,
    line_ip     TEXT NOT NULL DEFAULT '',
    event_type  TEXT NOT NULL CHECK (event_type IN ('cycle_complete', 'metal_detected')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_line_events_type_time
    ON line_events (event_type, occurred_at);
"""

MINUTE_COUNTS_SQL = """
SELECT
    to_char(gs, 'HH24:MI') AS minute,
    COUNT(*) FILTER (WHERE e.event_type = 'cycle_complete')  AS cycles,
    COUNT(*) FILTER (WHERE e.event_type = 'metal_detected')  AS metal
FROM generate_series(
    date_trunc('minute', now()) - make_interval(mins => %(window)s - 1),
    date_trunc('minute', now()),
    interval '1 minute'
) AS gs
LEFT JOIN line_events e
    ON e.occurred_at >= gs AND e.occurred_at < gs + interval '1 minute'
    AND e.line_ip = %(line_ip)s
GROUP BY gs
ORDER BY gs;
"""


def connect_db(dsn: str) -> Connection:
    return connect(dsn, connect_timeout=5)


def ensure_schema(dsn: str, default_line_ip: str = "") -> None:
    with connect_db(dsn) as conn:
        conn.execute(SCHEMA_SQL)
        row = conn.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'line_events' AND column_name = 'line_ip'"
        ).fetchone()
        if not row:
            # Pre-existing table from before the multi-line change.
            conn.execute("ALTER TABLE line_events ADD COLUMN line_ip TEXT NOT NULL DEFAULT ''")
        if default_line_ip:
            conn.execute(
                "UPDATE line_events SET line_ip = %s WHERE line_ip = ''",
                (default_line_ip,),
            )
        conn.commit()


def insert_event(dsn: str, event_type: str, line_ip: str = "") -> int:
    with connect_db(dsn) as conn:
        row = conn.execute(
            "INSERT INTO line_events (line_ip, event_type) VALUES (%s, %s) RETURNING id",
            (line_ip, event_type),
        ).fetchone()
        conn.commit()
        return row[0]


def per_minute_counts(
    dsn: str, window_minutes: int = 10, line_ip: str | None = None
) -> list[dict]:
    if window_minutes < 1:
        raise ValueError("window_minutes must be >= 1")
    with connect_db(dsn) as conn:
        rows = conn.execute(
            MINUTE_COUNTS_SQL, {"window": window_minutes, "line_ip": line_ip or ""}
        ).fetchall()
    return [
        {"minute": r[0], "cycles": r[1], "metal": r[2]} for r in rows
    ]
