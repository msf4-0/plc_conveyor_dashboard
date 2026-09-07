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
    cfg = load_config()
    create_database(cfg.database_url)
    ensure_schema(cfg.database_url, default_line_ip=cfg.plc_ip)
    print(f"Schema ensured: table line_events (+ index, line_ip default '{cfg.plc_ip}')")


if __name__ == "__main__":
    main()
