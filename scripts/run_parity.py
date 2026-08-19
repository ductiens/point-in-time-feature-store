import argparse
import os
from pathlib import Path
import sys

import redis

from pit_feature_store.catalog import CATALOG_PATH
from pit_feature_store.parity import (
    DEFAULT_ABS_TOL,
    DEFAULT_REL_TOL,
    DEFAULT_SAMPLE_SIZE,
    ParityResult,
    run_parity,
)
from pit_feature_store.warehouse import DATABASE_PATH


DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare sampled DuckDB offline features with the replayed Redis "
            "online store."
        )
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
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f"Number of rows to compare (minimum/default: {DEFAULT_SAMPLE_SIZE}).",
    )
    parser.add_argument(
        "--rel-tol",
        type=float,
        default=DEFAULT_REL_TOL,
        help=f"Relative float tolerance (default: {DEFAULT_REL_TOL}).",
    )
    parser.add_argument(
        "--abs-tol",
        type=float,
        default=DEFAULT_ABS_TOL,
        help=f"Absolute float tolerance (default: {DEFAULT_ABS_TOL}).",
    )
    return parser


def print_result(result: ParityResult) -> int:
    print(f"samples={result.sample_count}")
    print(f"features={','.join(result.feature_names)}")
    print(f"comparisons={result.comparison_count}")
    print(f"mismatches={result.mismatch_count}")
    for mismatch in result.mismatches:
        print(
            "MISMATCH "
            f"label_id={mismatch.label_id!r} "
            f"uid={mismatch.uid!r} "
            f"cutoff_ts={mismatch.cutoff_ts.isoformat()} "
            f"feature={mismatch.feature_name} "
            f"offline={mismatch.offline_value!r} "
            f"online={mismatch.online_value!r} "
            f"reason={mismatch.reason}"
        )

    if result.mismatch_count:
        print("FAILED: Offline/online parity có mismatch.")
        return 1
    print("OK: Offline/online parity có 0 mismatch.")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    arguments = build_parser().parse_args()
    redis_client = redis.Redis.from_url(arguments.redis_url)
    try:
        redis_client.ping()
        result = run_parity(
            redis_client,
            database_path=arguments.database_path,
            catalog_path=arguments.catalog_path,
            sample_size=arguments.sample_size,
            rel_tol=arguments.rel_tol,
            abs_tol=arguments.abs_tol,
        )
    finally:
        redis_client.close()

    return print_result(result)


if __name__ == "__main__":
    raise SystemExit(main())
