import sys
from pathlib import Path

import duckdb

from .catalog import CATALOG_PATH, FeatureCatalog, FeatureDefinition, load_catalog


DATABASE_PATH = Path("artifacts/warehouse.duckdb")

# Những giao dịch cần tính feature
def create_label_spine(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE OR REPLACE VIEW label_spine AS
        SELECT
            transaction_id AS label_id,
            uid,
            event_ts AS cutoff_ts,
            label
        FROM transactions
        """
    )

# Lịch sử giao dịch dùng để tính feature
def create_feature_events(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE OR REPLACE VIEW feature_events AS
        SELECT
            uid,
            event_ts AS feature_ts,
            amount,
            transaction_id AS event_id
        FROM transactions
        WHERE uid IS NOT NULL
        """
    )

# Tính tổng cộng dồn và số lượng giao dịch theo thời gian
def create_feature_cumsum(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE OR REPLACE VIEW feature_cumsum AS
        WITH events_by_timestamp AS (
            SELECT
                uid,
                feature_ts,
                SUM(amount) AS amount,
                MAX(event_id) AS event_id,
                COUNT(*) AS event_count
            FROM feature_events
            GROUP BY uid, feature_ts
        )
        SELECT
            uid,
            feature_ts,
            amount,
            event_id,
            SUM(amount) OVER (
                PARTITION BY uid
                ORDER BY feature_ts, event_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS cumulative_amount,
            SUM(event_count) OVER (
                PARTITION BY uid
                ORDER BY feature_ts
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS cumulative_count
        FROM events_by_timestamp
        """
    )

# đổi giá trị từ YAML sang SQL
def _default_sql(feature: FeatureDefinition) -> str:
    if feature.default_value is None:
        return "NULL"
    return repr(feature.default_value)

# tạo tên: lower_24h, lower_48h,...
def _lower_alias(window_hours: int) -> str:
    return f"lower_{window_hours}h"

# tính giá trị từ L đến R trong mảng cộng dồn
def _cumulative_feature_sql(feature: FeatureDefinition) -> str:
    cumulative_column = {
        "sum": "cumulative_amount",
        "count": "cumulative_count",
    }[feature.aggregation]
    default = _default_sql(feature)
    lower_alias = _lower_alias(feature.window_hours)

    expression = f"""
        COALESCE(end_values.{cumulative_column}, 0)
        -
        COALESCE({lower_alias}.{cumulative_column}, 0)
        """
    if default != "0":
        raise ValueError(
            f"Aggregation '{feature.aggregation}' requires default value 0."
        )
    return expression

# số giây từ giao dịch gần nhất đến thời điểm hiện tại
def _time_since_last_sql(feature: FeatureDefinition) -> str:
    window = feature.window_hours
    return f"""
        CASE
            WHEN end_values.feature_ts
                >= spine.cutoff_ts - INTERVAL '{window} hours'
            THEN date_diff(
                'second',
                end_values.feature_ts,
                spine.cutoff_ts
            )
            ELSE NULL
        END
        """

# điều phối tính toán feature dựa trên aggregation
def _feature_sql(feature: FeatureDefinition) -> str:
    if feature.aggregation in {"sum", "count"}:
        return _cumulative_feature_sql(feature)
    if feature.aggregation == "time_since_last":
        return _time_since_last_sql(feature)
    raise ValueError(f"Unsupported aggregation: {feature.aggregation}")

# tạo bảng kết quả cuối cùng
def create_pit_features(
    connection: duckdb.DuckDBPyConnection,
    catalog: FeatureCatalog,
) -> None:
    cumulative_windows = sorted(
        {
            feature.window_hours
            for feature in catalog.features
            if feature.aggregation in {"sum", "count"}
        }
    )
    feature_columns = ",\n".join(
        f"CAST(({_feature_sql(feature)}) AS "
        f"{'BIGINT' if feature.aggregation == 'count' else 'DOUBLE'}) "
        f"AS {feature.name}"
        for feature in catalog.features
    )
    lower_joins = "\n".join(
        f"""
        ASOF LEFT JOIN feature_cumsum AS {_lower_alias(window)}
          ON spine.uid = {_lower_alias(window)}.uid
         AND spine.cutoff_ts - INTERVAL '{window} hours'
             > {_lower_alias(window)}.feature_ts
        """
        for window in cumulative_windows
    )

    connection.execute(
        f"""
        CREATE OR REPLACE TABLE pit_features AS
        SELECT
            spine.label_id,
            spine.uid,
            spine.cutoff_ts,
            spine.label,
            {feature_columns}
        FROM label_spine AS spine
        ASOF LEFT JOIN feature_cumsum AS end_values
          ON spine.uid = end_values.uid
         AND spine.cutoff_ts > end_values.feature_ts
        {lower_joins}
        ORDER BY spine.cutoff_ts, spine.label_id
        """
    )


def build_offline_features(
    connection: duckdb.DuckDBPyConnection,
    catalog_path: Path = CATALOG_PATH,
) -> None:
    catalog = load_catalog(catalog_path)
    create_label_spine(connection)
    create_feature_events(connection)
    create_feature_cumsum(connection)
    create_pit_features(connection, catalog)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    connection = duckdb.connect(DATABASE_PATH.as_posix())
    try:
        build_offline_features(connection)
        row_count = connection.sql(
            "SELECT COUNT(*) FROM pit_features"
        ).fetchone()[0]
    finally:
        connection.close()

    print(
        f"OK: Đã tạo offline features tại {DATABASE_PATH.resolve()} "
        f"với {row_count:,} dòng."
    )


if __name__ == "__main__":
    main()
