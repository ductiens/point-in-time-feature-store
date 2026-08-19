import argparse
import os
from pathlib import Path
import sys

import redis

from pit_feature_store.catalog import CATALOG_PATH
from pit_feature_store.online_engine import replay_warehouse
from pit_feature_store.warehouse import DATABASE_PATH


DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay raw warehouse transactions into the Redis online store."
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=DATABASE_PATH,
        help=f"DuckDB warehouse path (default: {DATABASE_PATH}).",
    )
    parser.add_argument(
        "--catalog-path",
        type=Path,
        default=CATALOG_PATH,
        help=f"Feature catalog path (default: {CATALOG_PATH}).",
    )
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL", DEFAULT_REDIS_URL),
        help="Redis URL (default: REDIS_URL or redis://localhost:6379/0).",
    )
    return parser


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    arguments = build_parser().parse_args()
    redis_client = redis.Redis.from_url(arguments.redis_url)
    try:
        redis_client.ping()
        result = replay_warehouse(
            redis_client,
            database_path=arguments.database_path,
            catalog_path=arguments.catalog_path,
        )
    finally:
        redis_client.close()

    print(
        f"OK: Đã replay {result.total_rows:,} giao dịch; "
        f"ingest {result.ingested_events:,} event có UID."
    )
    print(f"virtual_now_epoch={result.last_event_epoch}")


if __name__ == "__main__":
    main()
