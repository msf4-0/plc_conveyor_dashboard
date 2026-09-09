"""OEE history database access: schema creation, inserts, latest, history.

Requires the local PostgreSQL server (the only DB-dependent tests left).
"""

import os

import pytest
from psycopg import connect

import app.config  # noqa: F401  (loads .env into the environment)
from app.db import (
    connect_db,
    ensure_oee_schema,
    insert_oee_row,
    latest_oee_row,
    oee_history,
)

OEE_TEST_DB = "plc_dashboard_oee_test"


@pytest.fixture(scope="module")
def oee_dsn():
    # Same server as the recorder's oee database (OEE_DATABASE_URL).
    base = os.environ["OEE_DATABASE_URL"]
    root, _, _ = base.rpartition("/")
    dsn = f"{root}/{OEE_TEST_DB}"
    admin = connect(f"{root}/postgres", autocommit=True)
    try:
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (OEE_TEST_DB,)
        ).fetchone()
        if not exists:
            admin.execute(f'CREATE DATABASE "{OEE_TEST_DB}"')
    finally:
        admin.close()
    ensure_oee_schema(dsn)
    return dsn


@pytest.fixture(autouse=True)
def clean_table(oee_dsn):
    yield
    with connect_db(oee_dsn) as conn:
        conn.execute("DELETE FROM oee")
        conn.commit()


def test_ensure_oee_schema_idempotent(oee_dsn):
    ensure_oee_schema(oee_dsn)
    ensure_oee_schema(oee_dsn)  # no error on re-run


def test_latest_empty_returns_none(oee_dsn):
    assert latest_oee_row(oee_dsn) is None


def test_insert_and_latest_round_trip(oee_dsn):
    insert_oee_row(oee_dsn, 91.5, 87.25, 98.0, 78.4)
    row = latest_oee_row(oee_dsn)
    assert set(row) == {"timestamp", "availability", "performance", "quality", "oee"}
    assert row["availability"] == pytest.approx(91.5)
    assert row["performance"] == pytest.approx(87.25)
    assert row["quality"] == pytest.approx(98.0)
    assert row["oee"] == pytest.approx(78.4)
    assert row["timestamp"]  # ISO string from the server clock


def test_latest_returns_most_recent_row(oee_dsn):
    insert_oee_row(oee_dsn, 10.0, 10.0, 10.0, 10.0)
    insert_oee_row(oee_dsn, 20.0, 20.0, 20.0, 20.0)
    assert latest_oee_row(oee_dsn)["oee"] == pytest.approx(20.0)


def test_null_metrics_persist(oee_dsn):
    insert_oee_row(oee_dsn, None, None, None, None)
    row = latest_oee_row(oee_dsn)
    assert row["availability"] is None
    assert row["performance"] is None
    assert row["quality"] is None
    assert row["oee"] is None


def test_history_window_excludes_old_rows(oee_dsn):
    insert_oee_row(oee_dsn, 1.0, 1.0, 1.0, 1.0)
    insert_oee_row(oee_dsn, 2.0, 2.0, 2.0, 2.0)
    with connect_db(oee_dsn) as conn:
        conn.execute(
            "UPDATE oee SET timestamp = now() - interval '2 hours' "
            "WHERE availability = 1.0"
        )
        conn.commit()
    history = oee_history(oee_dsn, minutes=10)
    assert len(history) == 1
    assert history[0]["oee"] == pytest.approx(2.0)


def test_history_ascending_order(oee_dsn):
    insert_oee_row(oee_dsn, 1.0, 1.0, 1.0, 1.0)
    insert_oee_row(oee_dsn, 2.0, 2.0, 2.0, 2.0)
    stamps = [r["timestamp"] for r in oee_history(oee_dsn, minutes=10)]
    assert stamps == sorted(stamps)


@pytest.mark.parametrize("bad", [0, -1])
def test_history_invalid_minutes_rejected(oee_dsn, bad):
    with pytest.raises(ValueError):
        oee_history(oee_dsn, minutes=bad)
