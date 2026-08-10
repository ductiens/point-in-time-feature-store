# Leakage experiment

## Setup

- Model: LightGBM classifier, random state `42`.
- Eligible cohort: `2018-01-01 00:00:00` to `2018-05-02 23:58:51`, so every cutoff has a complete 720-hour observation window on both sides.
- Rows: 370770 eligible, 219770 excluded from 590540 total.
- Split: 80/20 by `cutoff_ts`; train `< 2018-04-05 23:19:56`, test `>= 2018-04-05 23:19:56`.
- PIT uses `[cutoff - window, cutoff)`; leaky uses `(cutoff, cutoff + window]`.

## Future Feature Semantics

`future_only` keeps the PIT feature names to satisfy the spec. In the controlled comparison, future columns are renamed explicitly:

| Spec name | PIT + future name | Future semantics |
|---|---|---|
| `sum_amt_24h` | `future_sum_amt_24h` | Value in (cutoff, cutoff + 24h] |
| `count_txn_24h` | `future_count_txn_24h` | Value in (cutoff, cutoff + 24h] |
| `sum_amt_7d` | `future_sum_amt_7d` | Value in (cutoff, cutoff + 168h] |
| `time_since_last_txn_sec` | `time_to_next_txn_sec` | Seconds until the next future event |

## Results

The test fraud rate is `0.034077`, used as the random baseline for PR-AUC.

| Dataset | Features | ROC-AUC | PR-AUC | PR-AUC lift |
|---|---:|---:|---:|---:|
| PIT | 4 | 0.679783 | 0.067894 | 1.992x |
| Future-only | 4 | 0.674214 | 0.064931 | 1.905x |
| PIT + future | 8 | 0.705485 | 0.074536 | 2.187x |

## Analysis

The controlled comparison is `pit_plus_future` versus `pit`: ROC-AUC is higher by +0.025702, and PR-AUC is higher by +0.006641. The only difference is that the second model receives additional future features.

The spec comparison is `future_only` versus `pit`: ROC-AUC is lower by -0.005569, and PR-AUC is lower by -0.002963. This comparison also replaces past signal with future signal, so it is a secondary view.

The conclusion describes the observed experiment only; it does not assume future information must improve the metric.
