from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from .catalog import CATALOG_PATH, FeatureCatalog, FeatureDefinition, load_catalog
from .offline_engine import build_offline_features


TRAIN_FRACTION = 0.8


@dataclass(frozen=True)
class ObservationBounds:
    """Valid cutoff range for modeling.

    The leakage experiment needs a complete 720-hour window on both sides of
    each cutoff, so rows too close to the beginning or end are excluded before
    the temporal split.
    """

    start: pd.Timestamp
    end: pd.Timestamp
    total_rows: int # tổng số giao dịch trong toàn bộ dữ liệu
    eligible_rows: int # số giao dịch nằm trong khoảng hợp lệ

    @property
    def excluded_rows(self) -> int:
        return self.total_rows - self.eligible_rows

# danh sách tên feature
def feature_names(catalog: FeatureCatalog) -> list[str]:
    return [feature.name for feature in catalog.features]

# Trả tên của feature tương lai dựa trên định nghĩa feature. Nếu aggregation là "time_since_last", trả về "time_to_next_txn_sec", ngược lại trả về "future_" + tên feature.
def future_feature_name(feature: FeatureDefinition) -> str:
    if feature.aggregation == "time_since_last":
        return "time_to_next_txn_sec"
    return f"future_{feature.name}"

# Trả về danh sách tên các feature tương lai dựa trên catalog. Sử dụng hàm future_feature_name để lấy tên của từng feature trong catalog.
def future_feature_names(catalog: FeatureCatalog) -> list[str]:
    return [future_feature_name(feature) for feature in catalog.features]

# Hàm này tạo ra một alias cho bảng cumulative dựa trên số giờ của window. Ví dụ, nếu window_hours là 24, alias sẽ là "upper_24h".
def _upper_alias(window_hours: int) -> str:
    return f"upper_{window_hours}h"

# Hàm này tạo ra một đoạn SQL để tính toán giá trị feature tương lai dựa trên định nghĩa feature. Nếu aggregation là "sum" hoặc "count", nó sẽ tính toán giá trị tích lũy và trừ đi giá trị tại cutoff. Nếu aggregation là "time_since_last", nó sẽ tính toán thời gian kể từ sự kiện tiếp theo. Nếu aggregation không được hỗ trợ, nó sẽ ném ra lỗi.
def _future_feature_sql(feature: FeatureDefinition) -> str:
    if feature.aggregation in {"sum", "count"}:
        cumulative_column = {
            "sum": "cumulative_amount",
            "count": "cumulative_count",
        }[feature.aggregation]
        if feature.default_value != 0:
            raise ValueError(
                f"Aggregation '{feature.aggregation}' requires default value 0."
            )
        return f"""
            COALESCE({_upper_alias(feature.window_hours)}.{cumulative_column}, 0)
            - COALESCE(at_cutoff.{cumulative_column}, 0)
            """

    if feature.aggregation == "time_since_last":
        return f"""
            CASE
                WHEN next_event.feature_ts
                    <= spine.cutoff_ts
                       + INTERVAL '{feature.window_hours} hours'
                THEN date_diff(
                    'second',
                    spine.cutoff_ts,
                    next_event.feature_ts
                )
                ELSE NULL
            END
            """

    raise ValueError(f"Unsupported aggregation: {feature.aggregation}")

# Hàm này tạo ra bảng leaky_features với cùng schema feature như pit_features. Nó tính toán các giá trị feature tương lai dựa trên các định nghĩa feature trong catalog và lưu trữ chúng trong bảng leaky_features. Các giá trị feature được tính toán dựa trên các cửa sổ tích lũy và sự kiện tiếp theo, nếu cần.
def create_leaky_features(
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
    needs_next_event = any(
        feature.aggregation == "time_since_last"
        for feature in catalog.features
    )
    feature_columns = ",\n".join(
        f"CAST(({_future_feature_sql(feature)}) AS "
        f"{'BIGINT' if feature.aggregation == 'count' else 'DOUBLE'}) "
        f"AS {feature.name}"
        for feature in catalog.features
    )
    upper_joins = "\n".join(
        f"""
        ASOF LEFT JOIN feature_cumsum AS {_upper_alias(window)}
          ON spine.uid = {_upper_alias(window)}.uid
         AND spine.cutoff_ts + INTERVAL '{window} hours'
             >= {_upper_alias(window)}.feature_ts
        """
        for window in cumulative_windows
    )
    next_event_join = (
        """
        ASOF LEFT JOIN feature_cumsum AS next_event
          ON spine.uid = next_event.uid
         AND spine.cutoff_ts < next_event.feature_ts
        """
        if needs_next_event
        else ""
    )

    connection.execute(
        f"""
        CREATE OR REPLACE TABLE leaky_features AS
        SELECT
            spine.label_id,
            spine.uid,
            spine.cutoff_ts,
            spine.label,
            {feature_columns}
        FROM label_spine AS spine
        ASOF LEFT JOIN feature_cumsum AS at_cutoff
          ON spine.uid = at_cutoff.uid
         AND spine.cutoff_ts >= at_cutoff.feature_ts
        {upper_joins}
        {next_event_join}
        ORDER BY spine.cutoff_ts, spine.label_id
        """
    )

# Hàm này tạo ra một view pit_plus_future_features kết hợp các feature từ pit_features và leaky_features. Nó sử dụng các alias để đặt tên cho các feature tương lai dựa trên định nghĩa feature trong catalog. View này có thể được sử dụng để so sánh hiệu suất của các mô hình dựa trên các feature hiện tại và các feature tương lai.
def create_pit_plus_future_view(
    connection: duckdb.DuckDBPyConnection,
    catalog: FeatureCatalog,
) -> None:
    pit_columns = ",\n".join(
        f"pit.{feature.name} AS {feature.name}"
        for feature in catalog.features
    )
    future_columns = ",\n".join(
        f"future.{feature.name} AS {future_feature_name(feature)}"
        for feature in catalog.features
    )
    connection.execute(
        f"""
        CREATE OR REPLACE VIEW pit_plus_future_features AS
        SELECT
            pit.label_id,
            pit.uid,
            pit.cutoff_ts,
            pit.label,
            {pit_columns},
            {future_columns}
        FROM pit_features AS pit
        JOIN leaky_features AS future
          ON pit.label_id = future.label_id
        """
    )

# Hàm này xây dựng các dataset liên quan đến leakage. Nó tải catalog từ đường dẫn được cung cấp, xây dựng các feature offline, tạo các feature leaky và tạo view pit_plus_future. Cuối cùng, nó trả về catalog đã được xây dựng.
def build_leakage_datasets(
    connection: duckdb.DuckDBPyConnection,
    catalog_path: Path = CATALOG_PATH,
) -> FeatureCatalog:
    catalog = load_catalog(catalog_path)
    build_offline_features(connection, catalog_path)
    create_leaky_features(connection, catalog)
    create_pit_plus_future_view(connection, catalog)
    return catalog

# Hàm này tìm các giới hạn quan sát hợp lệ cho việc xây dựng mô hình. Nó tính toán thời gian bắt đầu và kết thúc dựa trên khoảng thời gian lookback được xác định trong catalog. Nó cũng đếm tổng số hàng và số hàng đủ điều kiện trong khoảng thời gian này. Nếu không thể xác định giới hạn quan sát từ dữ liệu, nó sẽ ném ra lỗi.
def find_observation_bounds(
    connection: duckdb.DuckDBPyConnection,
    catalog: FeatureCatalog,
) -> ObservationBounds:
    lookback = catalog.max_lookback_hours
    row = connection.execute(
        f"""
        WITH bounds AS (
            SELECT
                MIN(event_ts) + INTERVAL '{lookback} hours' AS start_ts,
                MAX(event_ts) - INTERVAL '{lookback} hours' AS end_ts,
                COUNT(*) AS total_rows
            FROM transactions
        )
        SELECT
            bounds.start_ts,
            bounds.end_ts,
            bounds.total_rows,
            COUNT(*) FILTER (
                WHERE transactions.event_ts >= bounds.start_ts
                  AND transactions.event_ts <= bounds.end_ts
            ) AS eligible_rows
        FROM transactions
        CROSS JOIN bounds
        GROUP BY bounds.start_ts, bounds.end_ts, bounds.total_rows
        """
    ).fetchone()
    if row is None or row[0] is None or row[1] is None:
        raise ValueError("Cannot determine observation bounds from an empty dataset.")
    bounds = ObservationBounds(
        start=pd.Timestamp(row[0]),
        end=pd.Timestamp(row[1]),
        total_rows=int(row[2]),
        eligible_rows=int(row[3]),
    )
    if bounds.start > bounds.end or bounds.eligible_rows == 0:
        raise ValueError(
            "Dataset does not span enough time for complete observation windows."
        )
    return bounds

# Hàm này chọn một timestamp để chia dữ liệu thành tập huấn luyện và tập kiểm tra dựa trên train_fraction. Nó sử dụng hàm quantile_disc để tìm giá trị cutoff_ts tại phần trăm train_fraction trong khoảng thời gian hợp lệ. Nếu train_fraction không nằm trong khoảng (0, 1) hoặc không thể chọn được timestamp từ dữ liệu, nó sẽ ném ra lỗi.
def choose_split_timestamp(
    connection: duckdb.DuckDBPyConnection,
    bounds: ObservationBounds,
    train_fraction: float = TRAIN_FRACTION,
) -> pd.Timestamp:
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1.")

    split_ts = connection.execute(
        f"""
        SELECT quantile_disc(cutoff_ts, {train_fraction})
        FROM pit_features
        WHERE cutoff_ts >= ? AND cutoff_ts <= ?
        """,
        [bounds.start.to_pydatetime(), bounds.end.to_pydatetime()],
    ).fetchone()[0]
    if split_ts is None:
        raise ValueError("Cannot choose a split timestamp from an empty dataset.")
    return pd.Timestamp(split_ts)

# Hàm này tải một DataFrame từ một bảng feature cụ thể (pit_features, leaky_features hoặc pit_plus_future_features) dựa trên các cột được chỉ định và giới hạn quan sát. Nó kiểm tra xem bảng có hợp lệ không, thực hiện truy vấn SQL để lấy dữ liệu, chuyển đổi cột cutoff_ts sang định dạng datetime và kiểm tra số lượng hàng đủ điều kiện. Nếu số lượng hàng không khớp với số lượng hàng đủ điều kiện, nó sẽ ném ra lỗi.
def load_feature_frame(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: list[str],
    bounds: ObservationBounds,
) -> pd.DataFrame:
    if table_name not in {
        "pit_features",
        "leaky_features",
        "pit_plus_future_features",
    }:
        raise ValueError(f"Unsupported feature table: {table_name}")
    selected = ", ".join(["label_id", "uid", "cutoff_ts", "label", *columns])
    frame = connection.execute(
        f"""
        SELECT {selected}
        FROM {table_name}
        WHERE cutoff_ts >= ? AND cutoff_ts <= ?
        ORDER BY cutoff_ts, label_id
        """,
        [bounds.start.to_pydatetime(), bounds.end.to_pydatetime()],
    ).df()
    frame["cutoff_ts"] = pd.to_datetime(frame["cutoff_ts"])
    if len(frame) != bounds.eligible_rows:
        raise ValueError(
            f"{table_name} has {len(frame)} eligible rows; "
            f"expected {bounds.eligible_rows}."
        )
    return frame

# đánh dấu dòng nào thuộc train và dòng nào thuộc test theo thời gian.
def temporal_masks(
    frame: pd.DataFrame,
    split_ts: pd.Timestamp,
) -> tuple[pd.Series, pd.Series]:
    train_mask = frame["cutoff_ts"] < split_ts
    test_mask = frame["cutoff_ts"] >= split_ts
    if not train_mask.any() or not test_mask.any():
        raise ValueError("Temporal split must produce non-empty train and test sets.")
    return train_mask, test_mask

# Hàm này chuẩn bị các DataFrame cho thí nghiệm leakage. Nó xây dựng các dataset liên quan đến leakage, tìm các giới hạn quan sát, chọn timestamp chia dữ liệu, tải các DataFrame từ các bảng feature và kiểm tra xem các DataFrame có cùng spine không. Cuối cùng, nó trả về một dictionary chứa catalog, bounds, split_ts, danh sách tên feature và các DataFrame.
def prepare_experiment_frames(
    connection: duckdb.DuckDBPyConnection,
    catalog_path: Path = CATALOG_PATH,
    train_fraction: float = TRAIN_FRACTION,
) -> dict[str, object]:
    catalog = build_leakage_datasets(connection, catalog_path)
    pit_columns = feature_names(catalog)
    future_columns = future_feature_names(catalog)
    augmented_columns = [*pit_columns, *future_columns]
    bounds = find_observation_bounds(connection, catalog)
    split_ts = choose_split_timestamp(connection, bounds, train_fraction)
    frames = {
        "pit": load_feature_frame(connection, "pit_features", pit_columns, bounds),
        "future_only": load_feature_frame(
            connection, "leaky_features", pit_columns, bounds
        ),
        "pit_plus_future": load_feature_frame(
            connection,
            "pit_plus_future_features",
            augmented_columns,
            bounds,
        ),
    }

    metadata_columns = ["label_id", "uid", "cutoff_ts", "label"]
    if not frames["pit"][metadata_columns].equals(
        frames["future_only"][metadata_columns]
    ) or not frames["pit"][metadata_columns].equals(
        frames["pit_plus_future"][metadata_columns]
    ):
        raise ValueError("Leakage datasets do not share the same spine.")

    return {
        "catalog": catalog,
        "bounds": bounds,
        "split_ts": split_ts,
        "pit_columns": pit_columns,
        "future_columns": future_columns,
        "augmented_columns": augmented_columns,
        "frames": frames,
    }
