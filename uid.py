import sys
from pathlib import Path

import duckdb
import pandas as pd


DATA_PATH = Path("data/raw/ieee/train_transaction.csv")
OUTPUT_PATH = Path("reports/entity_candidate_results.csv")


# Mỗi candidate là một nhóm cột được dùng để đại diện cho một entity.
CANDIDATES: dict[str, list[str]] = {
    "card1_addr1": [
        "card1",
        "addr1",
    ],
    "card1_card2_addr1": [
        "card1",
        "card2",
        "addr1",
    ],
    "card1_card2_card5_addr1": [
        "card1",
        "card2",
        "card5",
        "addr1",
    ],
    "card1_card2_addr1_D1": [
        "card1",
        "card2",
        "addr1",
        "D1",
    ],
}

SELECTED_CANDIDATE = "card1_card2_addr1"
SELECTION_REASON = (
    "Cân bằng độ phủ 87.45%, tỷ lệ entity lặp 60.49% và tỷ lệ dòng "
    "thuộc entity lặp 97.15%; chi tiết hơn card1 + addr1 nhưng không "
    "bị phân mảnh mạnh như candidate có D1."
)


def build_uid_expression(columns: list[str]) -> str:
    """Tạo biểu thức MD5 từ danh sách cột."""

    cast_columns = [
        f"CAST({column} AS VARCHAR)"
        for column in columns
    ]

    joined_columns = ", ".join(cast_columns)

    return f"md5(concat_ws('|', {joined_columns}))"


def build_valid_condition(columns: list[str]) -> str:
    """
    Chỉ tạo UID khi tất cả cột của candidate đều có dữ liệu.

    Không dùng COALESCE(..., 'na') ở bước đánh giá vì có thể gom rất
    nhiều dòng thiếu dữ liệu thành một entity giả khổng lồ.
    """

    return " AND ".join(
        f"{column} IS NOT NULL"
        for column in columns
    )


def evaluate_candidate(
    connection: duckdb.DuckDBPyConnection,
    name: str,
    columns: list[str],
) -> dict:
    uid_expression = build_uid_expression(columns)
    valid_condition = build_valid_condition(columns)

    query = f"""
        WITH candidate_rows AS (
            -- Tạo uid cho candidate hiện tại từ các cột được chọn.
            -- Nếu một trong các cột bị NULL thì uid = NULL để không tính nhầm entity thiếu dữ liệu.
            SELECT
                CASE
                    WHEN {valid_condition}
                    THEN {uid_expression}
                    ELSE NULL
                END AS uid
            FROM read_csv_auto(
                '{DATA_PATH.as_posix()}',
                header = true
            )
        ),

        entity_counts AS (
            -- Gom các dòng có uid hợp lệ theo entity và đếm số giao dịch của từng entity.
            -- n_txn là chỉ số chính để biết entity đó có xuất hiện lặp lại hay không.
            SELECT
                uid,
                COUNT(*) AS n_txn
            FROM candidate_rows
            WHERE uid IS NOT NULL
            GROUP BY uid
        )

        SELECT
            -- Đếm tất cả giao dịch, kể cả giao dịch có uid = NULL
            (SELECT COUNT(*) FROM candidate_rows) AS total_rows,

            (
                -- Số dòng tạo được uid hợp lệ cho candidate này.
                SELECT COUNT(*)
                FROM candidate_rows
                WHERE uid IS NOT NULL
            ) AS rows_with_uid,

            ROUND(
                -- Tỷ lệ coverage: bao nhiêu % giao dịch có uid hợp lệ.
                100.0 *
                (
                    SELECT COUNT(*)
                    FROM candidate_rows
                    WHERE uid IS NOT NULL
                ) /
                NULLIF(
                    (SELECT COUNT(*) FROM candidate_rows),
                    0
                ),
                2
            ) AS coverage_pct,

            -- Số entity khác nhau tạo được từ candidate.
            COUNT(*) AS n_entities,

            ROUND(
                -- % entity có ít nhất 2 giao dịch. phần lớn uid nên có n_txn >= 2.
                100.0 *
                COUNT(*) FILTER (WHERE n_txn >= 2) /
                NULLIF(COUNT(*), 0),
                2
            ) AS repeat_entity_pct,

            ROUND(
                -- Trong toàn bộ các giao dịch, có bao nhiêu % giao dịch thuộc về những khách hàng (entity) đã từng giao dịch ít nhất 2 lần?
                100.0 *
                SUM(n_txn) FILTER (WHERE n_txn >= 2) /
                NULLIF(SUM(n_txn), 0),
                2
            ) AS repeat_row_pct,

            -- Trung vị số giao dịch trên mỗi entity. Nghĩa là entity điển hình có khoảng 2 giao dịch.
            MEDIAN(n_txn) AS median_txn_per_entity,

            -- Mốc 95% số giao dịch/entity. Khoảng 95% entity có số giao dịch nhỏ hơn hoặc bằng giá trị này.
            APPROX_QUANTILE(n_txn, 0.95)
                AS p95_txn_per_entity,

            -- Lấy entity có nhiều giao dịch nhất.
            MAX(n_txn) AS max_txn_per_entity

        FROM entity_counts
    """

    row = connection.sql(query).fetchone()

    return {
        "candidate": name,
        "columns": " + ".join(columns),
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


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy dataset: {DATA_PATH.resolve()}"
        )

    connection = duckdb.connect()

    results = [
        evaluate_candidate(
            connection=connection,
            name=name,
            columns=columns,
        )
        for name, columns in CANDIDATES.items()
    ]

    connection.close()

    result_df = pd.DataFrame(results)
    result_df["selected"] = (
        result_df["candidate"] == SELECTED_CANDIDATE
    )
    result_df["selection_reason"] = result_df["selected"].map(
        {True: SELECTION_REASON, False: ""}
    )

    # Candidate có tỷ lệ entity với ít nhất 2 giao dịch cao hơn được hiển thị trước.
    result_df = result_df.sort_values(
        by=[
            "repeat_entity_pct",
            "coverage_pct",
        ],
        ascending=False,
    ).reset_index(drop=True)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_df.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 220)

    print("\nKẾT QUẢ ĐÁNH GIÁ PSEUDO-ENTITY\n")
    print(
        result_df.drop(
            columns=[
                "selected",
                "selection_reason",
            ]
        ).to_string(index=False)
    )

    print(
        f"\nĐã lưu kết quả tại: {OUTPUT_PATH.as_posix()}"
    )


if __name__ == "__main__":
    main()
