from psycopg import Connection, connect


def connect_db(dsn: str) -> Connection:
    return connect(dsn, connect_timeout=5)


# -- OEE history (database `oee`, table `oee`) -------------------------------
OEE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS oee (
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT now(),
    availability DOUBLE PRECISION,
    performance  DOUBLE PRECISION,
    quality      DOUBLE PRECISION,
    oee          DOUBLE PRECISION
);
"""

OEE_COLUMNS = ("timestamp", "availability", "performance", "quality", "oee")


def ensure_oee_schema(dsn: str) -> None:
    with connect_db(dsn) as conn:
        conn.execute(OEE_SCHEMA_SQL)
        conn.commit()


def test_oee_connection(dsn: str) -> None:
    """Raise if the `oee` database cannot be reached or queried."""
    with connect_db(dsn) as conn:
        conn.execute("SELECT 1")


def insert_oee_row(
    dsn: str,
    availability: float | None,
    performance: float | None,
    quality: float | None,
    oee: float | None,
) -> None:
    """Insert one OEE history row; `timestamp` defaults to the server clock."""
    with connect_db(dsn) as conn:
        conn.execute(
            "INSERT INTO oee (availability, performance, quality, oee) "
            "VALUES (%s, %s, %s, %s)",
            (availability, performance, quality, oee),
        )
        conn.commit()


def _oee_row_to_dict(row: tuple) -> dict:
    return dict(zip(OEE_COLUMNS, (row[0].isoformat(), row[1], row[2], row[3], row[4])))


def latest_oee_row(dsn: str) -> dict | None:
    """Return the most recent OEE row, or None when the table is empty."""
    with connect_db(dsn) as conn:
        row = conn.execute(
            "SELECT timestamp, availability, performance, quality, oee "
            "FROM oee ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
    return _oee_row_to_dict(row) if row else None


def oee_history(dsn: str, minutes: int = 10) -> list[dict]:
    """Return OEE rows (ascending) from the last `minutes` minutes."""
    if minutes < 1:
        raise ValueError("minutes must be >= 1")
    with connect_db(dsn) as conn:
        rows = conn.execute(
            "SELECT timestamp, availability, performance, quality, oee "
            "FROM oee WHERE timestamp >= now() - make_interval(mins => %s) "
            "ORDER BY timestamp",
            (minutes,),
        ).fetchall()
    return [_oee_row_to_dict(r) for r in rows]
