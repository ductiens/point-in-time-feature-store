from dataclasses import dataclass
from pathlib import Path
import re

import duckdb
import pandas as pd


DATA_PATH = Path("data/raw/ieee/train_transaction.csv")
OUTPUT_PATH = Path("artifacts/reports/entity_candidate_results.csv")


@dataclass(frozen=True)
class EntityCandidate:
    name: str
    columns: tuple[str, ...]
    required: bool = True


CANDIDATES = (
    EntityCandidate("card1_addr1", ("card1", "addr1")),
    EntityCandidate(
        "card1_card2_addr1",
        ("card1", "card2", "addr1"),
    ),
    EntityCandidate(
        "card1_card2_card5_addr1",
        ("card1", "card2", "card5", "addr1"),
        required=False,
    ),
    EntityCandidate(
        "card1_card2_addr1_D1",
        ("card1", "card2", "addr1", "D1"),
    ),
)

REPORT_COLUMNS = [
    "candidate",
    "columns",
    "total_rows",
    "rows_with_uid",
    "coverage_pct",
    "n_entities",
    "repeat_entity_pct",
    "repeat_row_pct",
    "median_txn_per_entity",
    "p95_txn_per_entity",
    "max_txn_per_entity",
]


def _quote_identifier(identifier: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe column name: {identifier!r}")
    return f'"{identifier}"'


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_uid_expression(columns: tuple[str, ...]) -> str:
    cast_columns = ", ".join(
        f"CAST({_quote_identifier(column)} AS VARCHAR)"
        for column in columns
    )
    return f"md5(concat_ws('|', {cast_columns}))"


def build_valid_condition(columns: tuple[str, ...]) -> str:
    return " AND ".join(
        f"{_quote_identifier(column)} IS NOT NULL"
        for column in columns
    )


def _create_source_view(
    connection: duckdb.DuckDBPyConnection,
    data_path: Path,
) -> None:
    connection.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW entity_selection_source AS
        SELECT *
        FROM read_csv_auto(
            {_sql_string(data_path.as_posix())},
            header = true
        )
        """
    )

    actual_columns = {
        row[0]
        for row in connection.sql(
            "DESCRIBE entity_selection_source"
        ).fetchall()
    }
    required_columns = {
        column
        for candidate in CANDIDATES
        for column in candidate.columns
    }
    missing_columns = required_columns - actual_columns
    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"Dataset thiếu các cột đánh giá entity: {missing_text}"
        )


def evaluate_candidate(
    connection: duckdb.DuckDBPyConnection,
    candidate: EntityCandidate,
) -> dict[str, int | float | str]:
    valid_condition = build_valid_condition(candidate.columns)
    uid_expression = build_uid_expression(candidate.columns)

    row = connection.sql(
        f"""
        WITH candidate_rows AS (
            SELECT
                CASE
                    WHEN {valid_condition}
                    THEN {uid_expression}
                    ELSE NULL
                END AS uid
            FROM entity_selection_source
        ),
        entity_counts AS (
            SELECT uid, COUNT(*) AS n_txn
            FROM candidate_rows
            WHERE uid IS NOT NULL
            GROUP BY uid
        )
        SELECT
            (SELECT COUNT(*) FROM candidate_rows) AS total_rows,
            (
                SELECT COUNT(*)
                FROM candidate_rows
                WHERE uid IS NOT NULL
            ) AS rows_with_uid,
            ROUND(
                100.0 * (
                    SELECT COUNT(*)
                    FROM candidate_rows
                    WHERE uid IS NOT NULL
                ) / NULLIF(
                    (SELECT COUNT(*) FROM candidate_rows),
                    0
                ),
                2
            ) AS coverage_pct,
            COUNT(*) AS n_entities,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE n_txn >= 2)
                / NULLIF(COUNT(*), 0),
                2
            ) AS repeat_entity_pct,
            ROUND(
                100.0 * SUM(n_txn) FILTER (WHERE n_txn >= 2)
                / NULLIF(SUM(n_txn), 0),
                2
            ) AS repeat_row_pct,
            MEDIAN(n_txn) AS median_txn_per_entity,
            APPROX_QUANTILE(n_txn, 0.95) AS p95_txn_per_entity,
            MAX(n_txn) AS max_txn_per_entity
        FROM entity_counts
        """
    ).fetchone()

    return {
        "candidate": candidate.name,
        "columns": " + ".join(candidate.columns),
        "total_rows": row[0],
        "rows_with_uid": row[1],
        "coverage_pct": row[2],
        "n_entities": row[3],
        "repeat_entity_pct": row[4],
        "repeat_row_pct": row[5],
        "median_txn_per_entity": row[6],
        "p95_txn_per_entity": row[7],
        "max_txn_per_entity": row[8],
    }


def generate_entity_candidate_results(
    data_path: Path = DATA_PATH,
) -> pd.DataFrame:
    if not data_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy dataset: {data_path.resolve()}"
        )

    connection = duckdb.connect()
    try:
        _create_source_view(connection, data_path)
        results = pd.DataFrame(
            evaluate_candidate(connection, candidate)
            for candidate in CANDIDATES
        )
    finally:
        connection.close()

    return results.sort_values(
        by=["repeat_entity_pct", "coverage_pct"],
        ascending=False,
    ).reset_index(drop=True)[REPORT_COLUMNS]


def export_entity_candidate_results(
    results: pd.DataFrame,
    output_path: Path = OUTPUT_PATH,
) -> Path:
    missing_columns = set(REPORT_COLUMNS) - set(results.columns)
    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"Entity report thiếu các cột metrics: {missing_text}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_path, index=False)
    return output_path
