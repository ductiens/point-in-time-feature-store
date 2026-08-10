import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from catalog import CATALOG_PATH, FeatureCatalog, FeatureDefinition, load_catalog
from offline_engine import DATABASE_PATH, build_offline_features


METRICS_PATH = Path("reports/leakage_metrics.csv")
REPORT_PATH = Path("reports/leakage_experiment.md")
TRAIN_FRACTION = 0.8
RANDOM_STATE = 42


@dataclass(frozen=True)
class ObservationBounds:
    """Khoang cutoff duoc phep dung cho modeling.

    Leakage experiment can ca du du lieu 720 gio o ca qua khu va tuong lai.
    Vi vay ta cat bo cac giao dich qua gan dau/cuoi dataset truoc khi split.
    """

    start: pd.Timestamp
    end: pd.Timestamp
    total_rows: int
    eligible_rows: int

    @property
    def excluded_rows(self) -> int:
        """So dong bi loai vi khong du observation window hai phia."""

        return self.total_rows - self.eligible_rows


def feature_names(catalog: FeatureCatalog) -> list[str]:
    """Lay dung danh sach ten feature tu catalog.
    Dung catalog giup PIT va leaky khong bi lech ten cot hoac thu tu cot.
    """

    return [feature.name for feature in catalog.features]


def future_feature_name(feature: FeatureDefinition) -> str:
    """Dat ten ro nghia cho cot future trong model PIT + future.
    Bang leaky_features van giu ten theo spec. Rieng view kiem soat can ten
    moi de nhin vao biet cot nao la thong tin tuong lai.
    """

    if feature.aggregation == "time_since_last":
        return "time_to_next_txn_sec"
    return f"future_{feature.name}"


def future_feature_names(catalog: FeatureCatalog) -> list[str]:
    """Tao danh sach ten cot future ro nghia cho tat ca feature trong catalog."""

    return [future_feature_name(feature) for feature in catalog.features]


def _upper_alias(window_hours: int) -> str:
    """Tao alias SQL cho moc cutoff + window, vi du upper_24h."""

    return f"upper_{window_hours}h"


def _future_feature_sql(feature: FeatureDefinition) -> str:
    """Sinh bieu thuc SQL tinh mot feature bang du lieu tuong lai.

    Sum/count lay khoang (cutoff, cutoff + window] bang cach lay cumulative
    tai upper bound tru cumulative tai cutoff. Time feature lay so giay toi
    event tuong lai gan nhat nam trong window.
    """

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


def create_leaky_features(
    connection: duckdb.DuckDBPyConnection,
    catalog: FeatureCatalog,
) -> None:
    """Tao bang leaky_features co cung schema feature voi PIT.

    Bang nay co chu dich sai point-in-time: moi feature nhin ve tuong lai.
    Muc dich la tao doi chung de do anh huong cua data leakage.
    """

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


def create_pit_plus_future_view(
    connection: duckdb.DuckDBPyConnection,
    catalog: FeatureCatalog,
) -> None:
    """Tao view gom 4 feature PIT cong 4 feature tuong lai.

    Day la phep thu kiem soat chinh: model thu hai giu nguyen tin hieu qua
    khu va chi duoc them thong tin tuong lai.
    """

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


def build_leakage_datasets(
    connection: duckdb.DuckDBPyConnection,
    catalog_path: Path = CATALOG_PATH,
) -> FeatureCatalog:
    """Chuan bi tat ca dataset can cho leakage experiment.

    Ham nay rebuild PIT tu offline engine, sau do tao leaky_features va view
    pit_plus_future_features tren cung mot label spine.
    """

    catalog = load_catalog(catalog_path)
    build_offline_features(connection, catalog_path)
    create_leaky_features(connection, catalog)
    create_pit_plus_future_view(connection, catalog)
    return catalog


def find_observation_bounds(
    connection: duckdb.DuckDBPyConnection,
    catalog: FeatureCatalog,
) -> ObservationBounds:
    """Tim vung cutoff co du lookback o ca hai phia.

    Neu max window la 720 gio, cutoff hop le phai >= min(event_ts)+720h va
    <= max(event_ts)-720h. Cach nay tranh viec future feature o cuoi dataset
    bi cat cut mot cach nhan tao.
    """

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


def choose_split_timestamp(
    connection: duckdb.DuckDBPyConnection,
    bounds: ObservationBounds,
    train_fraction: float = TRAIN_FRACTION,
) -> pd.Timestamp:
    """Chon moc split theo thoi gian sau khi da loc observation bounds.

    quantile_disc tra ve mot timestamp that trong du lieu. Train dung
    cutoff < split_ts, test dung cutoff >= split_ts, nen cac dong cung
    timestamp khong bi chia sang hai tap.
    """

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


def load_feature_frame(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: list[str],
    bounds: ObservationBounds,
) -> pd.DataFrame:
    """Doc mot bang/view feature thanh DataFrame de dua vao LightGBM.

    Ham chi cho phep cac bang da biet, loc dung observation bounds va kiem
    tra so dong de dam bao ba dataset dung cung mot cohort.
    """

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


def temporal_masks(
    frame: pd.DataFrame,
    split_ts: pd.Timestamp,
) -> tuple[pd.Series, pd.Series]:
    """Tao mask train/test theo cutoff_ts.

    Dau bang split_ts thuoc ve test set, giup moi giao dich cung timestamp
    nam cung mot phia cua split.
    """

    train_mask = frame["cutoff_ts"] < split_ts
    test_mask = frame["cutoff_ts"] >= split_ts
    if not train_mask.any() or not test_mask.any():
        raise ValueError("Temporal split must produce non-empty train and test sets.")
    return train_mask, test_mask


def train_and_evaluate(
    frame: pd.DataFrame,
    columns: list[str],
    split_ts: pd.Timestamp,
    dataset_name: str,
    bounds: ObservationBounds,
) -> dict[str, Any]:
    """Train mot LightGBM va tra ve metric/metadata cua dataset.

    Khong fill NaN thu cong: LightGBM xu ly missing value noi bo. Ham nay
    cung ghi fraud-rate cua test set lam baseline ngau nhien cho PR-AUC.
    """

    train_mask, test_mask = temporal_masks(frame, split_ts)
    train_labels = frame.loc[train_mask, "label"].astype(int)
    test_labels = frame.loc[test_mask, "label"].astype(int)
    if train_labels.nunique() < 2 or test_labels.nunique() < 2:
        raise ValueError("Both temporal partitions must contain both label classes.")

    model = LGBMClassifier(
        objective="binary",
        n_estimators=100,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        deterministic=True,
        force_col_wise=True,
        verbosity=-1,
    )
    model.fit(frame.loc[train_mask, columns], train_labels)
    probabilities = model.predict_proba(frame.loc[test_mask, columns])[:, 1]
    test_fraud_rate = float(test_labels.mean())
    pr_auc = float(average_precision_score(test_labels, probabilities))

    return {
        "dataset": dataset_name,
        "eligible_start": bounds.start.isoformat(sep=" "),
        "eligible_end": bounds.end.isoformat(sep=" "),
        "total_rows": bounds.total_rows,
        "eligible_rows": bounds.eligible_rows,
        "excluded_rows": bounds.excluded_rows,
        "split_ts": split_ts.isoformat(sep=" "),
        "train_rows": int(train_mask.sum()),
        "test_rows": int(test_mask.sum()),
        "train_positive": int(train_labels.sum()),
        "test_positive": int(test_labels.sum()),
        "test_fraud_rate": test_fraud_rate,
        "feature_count": len(columns),
        "feature_columns": "|".join(columns),
        "roc_auc": float(roc_auc_score(test_labels, probabilities)),
        "pr_auc": pr_auc,
        "pr_auc_lift": pr_auc / test_fraud_rate,
    }


def write_reports(
    results: list[dict[str, Any]],
    catalog: FeatureCatalog,
    metrics_path: Path = METRICS_PATH,
    report_path: Path = REPORT_PATH,
) -> None:
    """Ghi ket qua ra CSV cho may doc va Markdown cho nguoi doc.

    CSV giu day du metric/metadata. Markdown tom tat setup, baseline PR-AUC,
    mapping ten future feature va hai phep so sanh: chinh va phu.
    """

    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    metrics = pd.DataFrame(results)
    metrics.to_csv(metrics_path, index=False, float_format="%.10f")

    indexed = metrics.set_index("dataset")
    pit = indexed.loc["pit"]
    future_only = indexed.loc["future_only"]
    augmented = indexed.loc["pit_plus_future"]
    controlled_roc_delta = float(augmented["roc_auc"] - pit["roc_auc"])
    controlled_pr_delta = float(augmented["pr_auc"] - pit["pr_auc"])
    spec_roc_delta = float(future_only["roc_auc"] - pit["roc_auc"])
    spec_pr_delta = float(future_only["pr_auc"] - pit["pr_auc"])

    def comparison(delta: float) -> str:
        if delta > 0:
            return "cao hơn"
        if delta < 0:
            return "thấp hơn"
        return "bằng"

    mapping_rows = "\n".join(
        f"| `{feature.name}` | `{future_feature_name(feature)}` | "
        f"{'Thời gian tới event tương lai gần nhất' if feature.aggregation == 'time_since_last' else f'Giá trị trong (cutoff, cutoff + {feature.window_hours}h]'} |"
        for feature in catalog.features
    )

    report = f"""# Leakage experiment

## Thiết lập

- Model: LightGBM classifier, random state `{RANDOM_STATE}`.
- Cohort hợp lệ: `{pit['eligible_start']}` đến `{pit['eligible_end']}` để mọi cutoff có đủ {catalog.max_lookback_hours} giờ ở cả hai phía.
- Số dòng: {int(pit['eligible_rows'])} hợp lệ, loại {int(pit['excluded_rows'])} trên tổng {int(pit['total_rows'])}.
- Split: 80/20 theo `cutoff_ts`; train `< {pit['split_ts']}`, test `>= {pit['split_ts']}`.
- PIT dùng `[cutoff - window, cutoff)`; leaky dùng `(cutoff, cutoff + window]`.

## Ngữ nghĩa future feature

`future_only` giữ tên feature PIT để đáp ứng đặc tả. Trong phép thử kiểm soát, các cột tương lai được đổi tên rõ nghĩa:

| Tên theo spec | Tên trong PIT + future | Ngữ nghĩa future |
|---|---|---|
{mapping_rows}

## Kết quả

Tỷ lệ fraud trong test là `{pit['test_fraud_rate']:.6f}`, được dùng làm baseline ngẫu nhiên cho PR-AUC.

| Dataset | Số feature | ROC-AUC | PR-AUC | PR-AUC lift |
|---|---:|---:|---:|---:|
| PIT | {int(pit['feature_count'])} | {pit['roc_auc']:.6f} | {pit['pr_auc']:.6f} | {pit['pr_auc_lift']:.3f}x |
| Future-only | {int(future_only['feature_count'])} | {future_only['roc_auc']:.6f} | {future_only['pr_auc']:.6f} | {future_only['pr_auc_lift']:.3f}x |
| PIT + future | {int(augmented['feature_count'])} | {augmented['roc_auc']:.6f} | {augmented['pr_auc']:.6f} | {augmented['pr_auc_lift']:.3f}x |

## Phân tích

Phép thử kiểm soát là so sánh `pit_plus_future` với `pit`: ROC-AUC {comparison(controlled_roc_delta)} {controlled_roc_delta:+.6f} và PR-AUC {comparison(controlled_pr_delta)} {controlled_pr_delta:+.6f}. Khác biệt duy nhất là model thứ hai nhận thêm future feature.

Phép thử theo đặc tả là so sánh `future_only` với `pit`: ROC-AUC {comparison(spec_roc_delta)} {spec_roc_delta:+.6f} và PR-AUC {comparison(spec_pr_delta)} {spec_pr_delta:+.6f}. Phép thử này đồng thời thay tín hiệu quá khứ bằng tín hiệu tương lai nên chỉ được xem là kết quả phụ.

Kết luận chỉ mô tả kết quả thực nghiệm; không giả định trước rằng thông tin tương lai luôn làm metric tăng.
"""
    report_path.write_text(report, encoding="utf-8")


def run_experiment(
    database_path: Path = DATABASE_PATH,
    catalog_path: Path = CATALOG_PATH,
    metrics_path: Path = METRICS_PATH,
    report_path: Path = REPORT_PATH,
) -> list[dict[str, Any]]:
    """Chay tron ven leakage experiment tren warehouse DuckDB.

    Thu tu: build dataset, loc cohort hop le, chon split, load 3 dataset,
    kiem tra cung spine, train 3 model, ghi report va tra ket qua.
    """

    connection = duckdb.connect(database_path.as_posix())
    try:
        catalog = build_leakage_datasets(connection, catalog_path)
        pit_columns = feature_names(catalog)
        future_columns = future_feature_names(catalog)
        augmented_columns = [*pit_columns, *future_columns]
        bounds = find_observation_bounds(connection, catalog)
        split_ts = choose_split_timestamp(connection, bounds)
        pit_frame = load_feature_frame(
            connection, "pit_features", pit_columns, bounds
        )
        future_frame = load_feature_frame(
            connection, "leaky_features", pit_columns, bounds
        )
        augmented_frame = load_feature_frame(
            connection,
            "pit_plus_future_features",
            augmented_columns,
            bounds,
        )

        metadata_columns = ["label_id", "uid", "cutoff_ts", "label"]
        if not pit_frame[metadata_columns].equals(
            future_frame[metadata_columns]
        ) or not pit_frame[metadata_columns].equals(
            augmented_frame[metadata_columns]
        ):
            raise ValueError("Leakage datasets do not share the same spine.")

        results = [
            train_and_evaluate(
                pit_frame, pit_columns, split_ts, "pit", bounds
            ),
            train_and_evaluate(
                future_frame,
                pit_columns,
                split_ts,
                "future_only",
                bounds,
            ),
            train_and_evaluate(
                augmented_frame,
                augmented_columns,
                split_ts,
                "pit_plus_future",
                bounds,
            ),
        ]
    finally:
        connection.close()

    write_reports(results, catalog, metrics_path, report_path)
    return results


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    results = run_experiment()
    print(f"OK: Đã ghi metric tại {METRICS_PATH.resolve()}.")
    for result in results:
        print(
            f"{result['dataset']}: "
            f"ROC-AUC={result['roc_auc']:.6f}, "
            f"PR-AUC={result['pr_auc']:.6f}"
        )
    print(f"Báo cáo phân tích: {REPORT_PATH.resolve()}.")


if __name__ == "__main__":
    main()