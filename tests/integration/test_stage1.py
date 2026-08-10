from pathlib import Path

import duckdb
import pandas as pd

DATA_PATH = Path("data/raw/ieee/train_transaction.csv")
IDENTITY_PATH = Path("data/raw/ieee/train_identity.csv")
REPORT_PATH = Path("reports/entity_candidate_results.csv")
WAREHOUSE_PATH = Path("warehouse.duckdb")
SELECTED_CANDIDATE = "card1_card2_addr1"

EXPECTED_ROWS = 590_540
REQUIRED_SOURCE_COLUMNS = {
    "TransactionID",
    "TransactionDT",
    "TransactionAmt",
    "isFraud",
    "card1",
    "card2",
    "addr1",
    "D1",
}
REQUIRED_CANDIDATES = {
    "card1_addr1",
    "card1_card2_addr1",
    "card1_card2_addr1_D1",
}


def test_dataset_exists_and_has_required_shape() -> None:
    assert DATA_PATH.exists()
    assert IDENTITY_PATH.exists()

    connection = duckdb.connect()
    source = (
        "read_csv_auto("
        f"'{DATA_PATH.as_posix()}', header = true"
        ")"
    )
    columns = {
        row[0]
        for row in connection.sql(
            f"DESCRIBE SELECT * FROM {source}"
        ).fetchall()
    }
    row_count = connection.sql(
        f"SELECT COUNT(*) FROM {source}"
    ).fetchone()[0]
    connection.close()

    assert row_count == EXPECTED_ROWS
    assert REQUIRED_SOURCE_COLUMNS <= columns


def test_entity_report_has_required_candidates_and_selection() -> None:
    report = pd.read_csv(REPORT_PATH)

    assert len(report) >= 3
    assert REQUIRED_CANDIDATES <= set(report["candidate"])
    assert {
        "n_entities",
        "repeat_entity_pct",
        "max_txn_per_entity",
        "median_txn_per_entity",
        "selected",
        "selection_reason",
    } <= set(report.columns)

    selected = report.loc[report["selected"]]
    assert selected["candidate"].tolist() == [SELECTED_CANDIDATE]
    assert selected["selection_reason"].str.strip().ne("").all()


def test_warehouse_shape_and_selected_uid_formula() -> None:
    connection = duckdb.connect(WAREHOUSE_PATH.as_posix(), read_only=True)

    columns = {
        row[0]
        for row in connection.sql(
            "DESCRIBE transactions"
        ).fetchall()
    }
    summary = connection.sql(
        """
        SELECT
            COUNT(*) AS total_rows,
            COUNT(*) - COUNT(DISTINCT transaction_id) AS duplicate_ids,
            COUNT(*) FILTER (
                WHERE event_ts IS NULL
                   OR amount IS NULL
                   OR label IS NULL
            ) AS invalid_required_values
        FROM transactions
        """
    ).fetchone()
    uid_mismatches = connection.sql(
        f"""
        SELECT COUNT(*)
        FROM transactions AS warehouse
        JOIN read_csv_auto(
            '{DATA_PATH.as_posix()}',
            header = true
        ) AS source
          ON warehouse.transaction_id = source.TransactionID
        WHERE warehouse.uid IS DISTINCT FROM
            CASE
                WHEN source.card1 IS NOT NULL
                 AND source.card2 IS NOT NULL
                 AND source.addr1 IS NOT NULL
                THEN md5(concat_ws(
                    '|',
                    CAST(source.card1 AS VARCHAR),
                    CAST(source.card2 AS VARCHAR),
                    CAST(source.addr1 AS VARCHAR)
                ))
                ELSE NULL
            END
        """
    ).fetchone()[0]
    connection.close()

    assert {
        "transaction_id",
        "uid",
        "event_ts",
        "amount",
        "label",
    } <= columns
    assert summary == (EXPECTED_ROWS, 0, 0)
    assert uid_mismatches == 0
