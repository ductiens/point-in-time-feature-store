import pandas as pd
import pytest

from test_offline_correctness import BASE_TS, create_connection


def feature_row(
    history_offset_hours: float,
) -> tuple[float, int, float, float | None]:
    connection = create_connection(
        [
            (
                1,
                "entity-a",
                BASE_TS - pd.Timedelta(hours=history_offset_hours),
                10.0,
                0,
            ),
            (2, "entity-a", BASE_TS, 99.0, 1),
            (3, "entity-a", BASE_TS + pd.Timedelta(hours=1), 500.0, 0),
        ]
    )
    try:
        return connection.sql(
            """
            SELECT
                sum_amt_24h,
                count_txn_24h,
                sum_amt_7d,
                time_since_last_txn_sec
            FROM pit_features
            WHERE label_id = 2
            """
        ).fetchone()
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("offset_hours", "sum_24h", "count_24h", "sum_7d", "last_seconds"),
    [
        (24, 10.0, 1, 10.0, 24 * 3600.0),
        (24.5, 0.0, 0, 10.0, 24.5 * 3600.0),
        (168, 0.0, 0, 10.0, 168 * 3600.0),
        (168.5, 0.0, 0, 0.0, 168.5 * 3600.0),
        (720, 0.0, 0, 0.0, 720 * 3600.0),
        (720.5, 0.0, 0, 0.0, None),
    ],
)
def test_window_boundaries_and_large_gaps(
    offset_hours: float,
    sum_24h: float,
    count_24h: int,
    sum_7d: float,
    last_seconds: float | None,
) -> None:
    actual = feature_row(offset_hours)
    expected = (sum_24h, count_24h, sum_7d, last_seconds)
    assert actual == expected


def test_events_at_cutoff_and_in_future_are_excluded() -> None:
    connection = create_connection(
        [
            (1, "entity-a", BASE_TS - pd.Timedelta(hours=1), 10.0, 0),
            (2, "entity-a", BASE_TS, 20.0, 0),
            (3, "entity-a", BASE_TS, 30.0, 1),
            (4, "entity-a", BASE_TS + pd.Timedelta(hours=1), 100.0, 0),
        ]
    )
    try:
        rows = connection.sql(
            """
            SELECT
                label_id,
                sum_amt_24h,
                count_txn_24h,
                time_since_last_txn_sec
            FROM pit_features
            WHERE label_id IN (2, 3)
            ORDER BY label_id
            """
        ).fetchall()
    finally:
        connection.close()

    assert rows == [
        (2, 10.0, 1, 3600.0),
        (3, 10.0, 1, 3600.0),
    ]
