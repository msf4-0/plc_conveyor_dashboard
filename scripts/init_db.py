import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from psycopg import connect

from app.config import load_recorder_config
from app.db import ensure_oee_schema


def create_database(dsn: str) -> None:
    base_dsn, _, dbname = dsn.rpartition("/")
    admin = connect(base_dsn + "/postgres", autocommit=True)
    try:
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
        ).fetchone()
        if not exists:
            admin.execute(f'CREATE DATABASE "{dbname}"')
            print(f"Created database '{dbname}'")
        else:
            print(f"Database '{dbname}' already exists")
    finally:
        admin.close()


def main() -> None:
    # OEE recorder database (history rows) — requires OEE_DATABASE_URL.
    # The dashboard itself needs no database: per-minute counts are in-memory.
    rec = load_recorder_config()
    create_database(rec.oee_database_url)
    ensure_oee_schema(rec.oee_database_url)
    print(f"Schema ensured: table oee in '{rec.oee_database_url.rpartition('/')[2]}'")


if __name__ == "__main__":
    main()
