import argparse
import sys

from pit_feature_store.backfill import run_backfill


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill point-in-time correct offline features."
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Inclusive start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="Inclusive end date in YYYY-MM-DD format.",
    )
    return parser


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    arguments = build_parser().parse_args()
    result = run_backfill(arguments.start_date, arguments.end_date)
    print(
        f"OK: Đã backfill {result.row_count:,} dòng vào "
        f"{result.output_path.resolve()}"
    )
    print(
        f"catalog_version={result.version} "
        f"lookback_hours={result.lookback_hours}"
    )


if __name__ == "__main__":
    main()
