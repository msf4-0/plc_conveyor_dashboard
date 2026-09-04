import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from psycopg import connect

from app.config import load_config
from app.db import ensure_schema


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
    dsn = load_config().database_url
    create_database(dsn)
    ensure_schema(dsn)
    print("Schema ensured: table line_events (+ index)")


if __name__ == "__main__":
    main()
