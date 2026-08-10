import sys
from pathlib import Path

import duckdb


DATA_PATH = Path("data/raw/ieee/train_transaction.csv")
DATABASE_PATH = Path("warehouse.duckdb")
EXPECTED_ROW_COUNT = 590_540

# Các cột bắt buộc phải có trong file IEEE-CIS.
REQUIRED_COLUMNS = {
    "TransactionID",
    "TransactionDT",
    "TransactionAmt",
    "isFraud",
    "card1",
    "card2",
    "addr1",
}


def validate_source_columns(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """Kiểm tra file CSV có đầy đủ các cột cần thiết."""

    columns = {
        row[0]
        for row in connection.sql(
            f"""
            DESCRIBE
            SELECT *
            FROM read_csv_auto(
                '{DATA_PATH.as_posix()}',
                header = true
            )
            """
        ).fetchall()
    }

    missing_columns = REQUIRED_COLUMNS - columns

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"Dataset thiếu các cột bắt buộc: {missing_text}"
        )


def create_transactions_table(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """
    Tạo bảng transactions.

    Chỉ tạo UID khi card1, card2 và addr1 đều có dữ liệu.
    """

    connection.sql(
        f"""
        CREATE OR REPLACE TABLE transactions AS

        SELECT
            CAST(TransactionID AS BIGINT) AS transaction_id,

            CASE
                WHEN card1 IS NOT NULL
                 AND card2 IS NOT NULL
                 AND addr1 IS NOT NULL
                THEN md5(
                    concat_ws(
                        '|',
                        CAST(card1 AS VARCHAR),
                        CAST(card2 AS VARCHAR),
                        CAST(addr1 AS VARCHAR)
                    )
                )
                ELSE NULL
            END AS uid,

            TIMESTAMP '2017-12-01 00:00:00'
                + CAST(TransactionDT AS BIGINT)
                * INTERVAL 1 SECOND
                AS event_ts,

            CAST(TransactionAmt AS DOUBLE)
                AS amount,

            CAST(isFraud AS UTINYINT)
                AS label

        FROM read_csv_auto(
            '{DATA_PATH.as_posix()}',
            header = true
        )

        ORDER BY
            TransactionDT,
            TransactionID
        """
    )


def validate_transactions_table(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """Kiểm tra các lỗi dữ liệu nghiêm trọng."""

    validation = connection.sql(
        """
        SELECT
            COUNT(*) AS total_rows,
            COUNT(*) - COUNT(DISTINCT transaction_id)
                AS duplicate_transaction_ids,
            COUNT(*) FILTER (
                WHERE transaction_id IS NULL
            ) AS null_transaction_ids,
            COUNT(*) FILTER (
                WHERE event_ts IS NULL OR amount IS NULL
            ) AS null_required_values,
            COUNT(*) FILTER (
                WHERE label IS NULL OR label NOT IN (0, 1)
            ) AS invalid_labels
        FROM transactions
        """
    ).fetchone()

    (
        total_rows,
        duplicate_transaction_ids,
        null_transaction_ids,
        null_required_values,
        invalid_labels,
    ) = validation

    entity_stats = connection.sql(
        """
        WITH entity_counts AS (
            SELECT uid, COUNT(*) AS n_txn
            FROM transactions
            WHERE uid IS NOT NULL
            GROUP BY uid
        )
        SELECT
            COUNT(*) AS n_entities,
            COUNT(*) FILTER (WHERE n_txn >= 2)
                AS repeated_entities
        FROM entity_counts
        """
    ).fetchone()

    n_entities, repeated_entities = entity_stats

    if total_rows != EXPECTED_ROW_COUNT:
        raise ValueError(
            f"Số dòng không đúng: cần {EXPECTED_ROW_COUNT:,}, "
            f"nhận được {total_rows:,}."
        )

    if duplicate_transaction_ids > 0:
        raise ValueError(
            f"Phát hiện {duplicate_transaction_ids} TransactionID trùng."
        )

    if null_transaction_ids > 0:
        raise ValueError(
            f"Phát hiện {null_transaction_ids} TransactionID bị NULL."
        )

    if null_required_values > 0:
        raise ValueError(
            f"Phát hiện {null_required_values} dòng thiếu event_ts hoặc amount."
        )

    if invalid_labels > 0:
        raise ValueError(
            f"Phát hiện {invalid_labels} label không hợp lệ."
        )

    if n_entities == 0 or repeated_entities * 2 <= n_entities:
        raise ValueError(
            "Không đạt yêu cầu: phần lớn UID phải có ít nhất 2 giao dịch."
        )


def print_summary(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """In thống kê để xác nhận warehouse được tạo đúng."""

    print("\nTHỐNG KÊ BẢNG TRANSACTIONS\n")

    connection.sql(
        """
        SELECT
            -- Tổng số giao dịch trong bảng transactions.
            COUNT(*) AS total_rows,

            -- Số TransactionID duy nhất sau khi đổi tên thành transaction_id.
            COUNT(DISTINCT transaction_id)
                AS distinct_transaction_ids,

            -- Số giao dịch tạo được pseudo-entity uid hợp lệ.
            COUNT(*) FILTER (WHERE uid IS NOT NULL)
                AS rows_with_uid,

            ROUND(
                -- Tỷ lệ % giao dịch có uid hợp lệ.
                100.0
                * COUNT(*) FILTER (WHERE uid IS NOT NULL)
                / COUNT(*),
                2
            ) AS uid_coverage_pct,

            ROUND(
                -- Tỷ lệ fraud trung bình vì label chỉ gồm 0 và 1.
                -- AVG(label) * 100 chính là % giao dịch gian lận.
                100.0 * AVG(label),
                4
            ) AS fraud_rate_pct,

            -- Khoảng thời gian sớm nhất và muộn nhất trong bảng.
            -- Dùng để kiểm tra event_ts đã được chuyển thành timestamp đúng.
            MIN(event_ts) AS min_event_ts,
            MAX(event_ts) AS max_event_ts

        FROM transactions
        """
    ).show()

    print("\nTHỐNG KÊ PSEUDO-ENTITY HỢP LỆ\n")

    connection.sql(
        """
        WITH entity_counts AS (
            -- Gom các giao dịch có uid hợp lệ theo từng pseudo-entity.
            -- n_txn là số giao dịch của mỗi uid, dùng để kiểm tra uid có lặp lại hay không.
            SELECT
                uid,
                COUNT(*) AS n_txn
            FROM transactions
            WHERE uid IS NOT NULL
            GROUP BY uid
        )

        SELECT
            -- Tổng số pseudo-entity hợp lệ tạo được từ bảng transactions.
            COUNT(*) AS n_entities,

            ROUND(
                -- % pseudo-entity có ít nhất 2 giao dịch.
                100.0
                * COUNT(*) FILTER (WHERE n_txn >= 2)
                / COUNT(*),
                2
            ) AS repeat_entity_pct,

            ROUND(
                -- % giao dịch nằm trong các pseudo-entity có ít nhất 2 giao dịch.
                100.0
                * SUM(n_txn) FILTER (WHERE n_txn >= 2)
                / SUM(n_txn),
                2
            ) AS repeat_row_pct,

            -- Trung vị số giao dịch trên mỗi pseudo-entity. Nếu median >= 2 thì entity lặp lại là khá phổ biến.
            MEDIAN(n_txn) AS median_txn_per_entity,

            -- Mốc 95% số giao dịch trên mỗi pseudo-entity.
            APPROX_QUANTILE(n_txn, 0.95)
                AS p95_txn_per_entity,

            -- Số giao dịch lớn nhất của một pseudo-entity.
            MAX(n_txn) AS max_txn_per_entity

        FROM entity_counts
        """
    ).show()

    print("\n5 DÒNG ĐẦU TIÊN\n")

    connection.sql(
        """
        -- Xem nhanh 5 dòng đầu để kiểm tra trực quan schema và dữ liệu mẫu.
        SELECT *
        FROM transactions
        LIMIT 5
        """
    ).show()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy dataset: {DATA_PATH.resolve()}"
        )

    connection = duckdb.connect(
        DATABASE_PATH.as_posix()
    )

    try:
        validate_source_columns(connection)
        create_transactions_table(connection)
        validate_transactions_table(connection)
        print_summary(connection)
    finally:
        connection.close()

    print(
        f"\nOK: Đã tạo warehouse tại "
        f"{DATABASE_PATH.resolve()}"
    )


if __name__ == "__main__":
    main()
