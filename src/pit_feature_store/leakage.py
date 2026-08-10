from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from .catalog import CATALOG_PATH, FeatureCatalog, FeatureDefinition, load_catalog
from .offline_engine import DATABASE_PATH, build_offline_features


TRAIN_FRACTION = 0.8
RANDOM_STATE = 42


@dataclass(frozen=True)
class ObservationBounds:
    """Valid cutoff range for modeling.

    The leakage experiment needs a complete 720-hour window on both sides of
    each cutoff, so rows too close to the beginning or end are excluded before
    the temporal split.
    """

    start: pd.Timestamp
    end: pd.Timestamp
    total_rows: int
    eligible_rows: int

    @property
    def excluded_rows(self) -> int:
        return self.total_rows - self.eligible_rows


def feature_names(catalog: FeatureCatalog) -> list[str]:
    return [feature.name for feature in catalog.features]


def future_feature_name(feature: FeatureDefinition) -> str:
    if feature.aggregation == "time_since_last":
        return "time_to_next_txn_sec"
    return f"future_{feature.name}"


def future_feature_names(catalog: FeatureCatalog) -> list[str]:
    return [future_feature_name(feature) for feature in catalog.features]


def _upper_alias(window_hours: int) -> str:
    return f"upper_{window_hours}h"


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


def create_leaky_features(
    connection: duckdb.DuckDBPyConnection,
    catalog: FeatureCatalog,
) -> None:
    """Create leaky_features with the same feature schema as pit_features."""

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
    catalog = load_catalog(catalog_path)
    build_offline_features(connection, catalog_path)
    create_leaky_features(connection, catalog)
    create_pit_plus_future_view(connection, catalog)
    return catalog


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


def temporal_masks(
    frame: pd.DataFrame,
    split_ts: pd.Timestamp,
) -> tuple[pd.Series, pd.Series]:
    train_mask = frame["cutoff_ts"] < split_ts
    test_mask = frame["cutoff_ts"] >= split_ts
    if not train_mask.any() or not test_mask.any():
        raise ValueError("Temporal split must produce non-empty train and test sets.")
    return train_mask, test_mask


def train_score_and_evaluate(
    frame: pd.DataFrame,
    columns: list[str],
    split_ts: pd.Timestamp,
    dataset_name: str,
    bounds: ObservationBounds,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Train one LightGBM model and return metrics plus test predictions."""

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

    metrics = {
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
    prediction_columns = [
        column
        for column in ["label_id", "cutoff_ts", "label"]
        if column in frame.columns
    ]
    predictions = frame.loc[test_mask, prediction_columns].copy()
    if "label_id" not in predictions.columns:
        predictions.insert(0, "label_id", predictions.index)
    predictions["dataset"] = dataset_name
    predictions["score"] = probabilities
    predictions = predictions[
        ["dataset", "label_id", "cutoff_ts", "label", "score"]
    ]
    return metrics, predictions


def train_and_evaluate(
    frame: pd.DataFrame,
    columns: list[str],
    split_ts: pd.Timestamp,
    dataset_name: str,
    bounds: ObservationBounds,
) -> dict[str, Any]:
    metrics, _ = train_score_and_evaluate(
        frame, columns, split_ts, dataset_name, bounds
    )
    return metrics


def prepare_experiment_frames(
    connection: duckdb.DuckDBPyConnection,
    catalog_path: Path = CATALOG_PATH,
) -> dict[str, Any]:
    catalog = build_leakage_datasets(connection, catalog_path)
    pit_columns = feature_names(catalog)
    future_columns = future_feature_names(catalog)
    augmented_columns = [*pit_columns, *future_columns]
    bounds = find_observation_bounds(connection, catalog)
    split_ts = choose_split_timestamp(connection, bounds)
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


def run_experiment(
    database_path: Path = DATABASE_PATH,
    catalog_path: Path = CATALOG_PATH,
) -> dict[str, Any]:
    connection = duckdb.connect(database_path.as_posix())
    try:
        prepared = prepare_experiment_frames(connection, catalog_path)
        columns_by_dataset = {
            "pit": prepared["pit_columns"],
            "future_only": prepared["pit_columns"],
            "pit_plus_future": prepared["augmented_columns"],
        }
        metric_rows = []
        prediction_frames = []
        for dataset_name in ["pit", "future_only", "pit_plus_future"]:
            metrics, predictions = train_score_and_evaluate(
                prepared["frames"][dataset_name],
                columns_by_dataset[dataset_name],
                prepared["split_ts"],
                dataset_name,
                prepared["bounds"],
            )
            metric_rows.append(metrics)
            prediction_frames.append(predictions)
    finally:
        connection.close()

    metrics_frame = pd.DataFrame(metric_rows)
    predictions_frame = pd.concat(prediction_frames, ignore_index=True)
    return {
        "catalog": prepared["catalog"],
        "metrics": metrics_frame,
        "predictions": predictions_frame,
        "markdown": render_report_markdown(metric_rows, prepared["catalog"]),
    }


def render_report_markdown(
    results: list[dict[str, Any]],
    catalog: FeatureCatalog,
) -> str:
    metrics = pd.DataFrame(results)
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
            return "higher"
        if delta < 0:
            return "lower"
        return "equal"

    mapping_rows = "\n".join(
        f"| `{feature.name}` | `{future_feature_name(feature)}` | "
        f"{'Seconds until the next future event' if feature.aggregation == 'time_since_last' else f'Value in (cutoff, cutoff + {feature.window_hours}h]'} |"
        for feature in catalog.features
    )

    return f"""# Leakage experiment

## Setup

- Model: LightGBM classifier, random state `{RANDOM_STATE}`.
- Eligible cohort: `{pit['eligible_start']}` to `{pit['eligible_end']}`, so every cutoff has a complete {catalog.max_lookback_hours}-hour observation window on both sides.
- Rows: {int(pit['eligible_rows'])} eligible, {int(pit['excluded_rows'])} excluded from {int(pit['total_rows'])} total.
- Split: 80/20 by `cutoff_ts`; train `< {pit['split_ts']}`, test `>= {pit['split_ts']}`.
- PIT uses `[cutoff - window, cutoff)`; leaky uses `(cutoff, cutoff + window]`.

## Future Feature Semantics

`future_only` keeps the PIT feature names to satisfy the spec. In the controlled comparison, future columns are renamed explicitly:

| Spec name | PIT + future name | Future semantics |
|---|---|---|
{mapping_rows}

## Results

The test fraud rate is `{pit['test_fraud_rate']:.6f}`, used as the random baseline for PR-AUC.

| Dataset | Features | ROC-AUC | PR-AUC | PR-AUC lift |
|---|---:|---:|---:|---:|
| PIT | {int(pit['feature_count'])} | {pit['roc_auc']:.6f} | {pit['pr_auc']:.6f} | {pit['pr_auc_lift']:.3f}x |
| Future-only | {int(future_only['feature_count'])} | {future_only['roc_auc']:.6f} | {future_only['pr_auc']:.6f} | {future_only['pr_auc_lift']:.3f}x |
| PIT + future | {int(augmented['feature_count'])} | {augmented['roc_auc']:.6f} | {augmented['pr_auc']:.6f} | {augmented['pr_auc_lift']:.3f}x |

## Analysis

The controlled comparison is `pit_plus_future` versus `pit`: ROC-AUC is {comparison(controlled_roc_delta)} by {controlled_roc_delta:+.6f}, and PR-AUC is {comparison(controlled_pr_delta)} by {controlled_pr_delta:+.6f}. The only difference is that the second model receives additional future features.

The spec comparison is `future_only` versus `pit`: ROC-AUC is {comparison(spec_roc_delta)} by {spec_roc_delta:+.6f}, and PR-AUC is {comparison(spec_pr_delta)} by {spec_pr_delta:+.6f}. This comparison also replaces past signal with future signal, so it is a secondary view.

The conclusion describes the observed experiment only; it does not assume future information must improve the metric.
"""
