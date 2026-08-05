# Leakage experiment

## Thiết lập

- Model: LightGBM classifier, random state `42`.
- Cohort hợp lệ: `2018-01-01 00:00:00` đến `2018-05-02 23:58:51` để mọi cutoff có đủ 720 giờ ở cả hai phía.
- Số dòng: 370770 hợp lệ, loại 219770 trên tổng 590540.
- Split: 80/20 theo `cutoff_ts`; train `< 2018-04-05 23:19:56`, test `>= 2018-04-05 23:19:56`.
- PIT dùng `[cutoff - window, cutoff)`; leaky dùng `(cutoff, cutoff + window]`.

## Ngữ nghĩa future feature

`future_only` giữ tên feature PIT để đáp ứng đặc tả. Trong phép thử kiểm soát, các cột tương lai được đổi tên rõ nghĩa:

| Tên theo spec | Tên trong PIT + future | Ngữ nghĩa future |
|---|---|---|
| `sum_amt_24h` | `future_sum_amt_24h` | Giá trị trong (cutoff, cutoff + 24h] |
| `count_txn_24h` | `future_count_txn_24h` | Giá trị trong (cutoff, cutoff + 24h] |
| `sum_amt_7d` | `future_sum_amt_7d` | Giá trị trong (cutoff, cutoff + 168h] |
| `time_since_last_txn_sec` | `time_to_next_txn_sec` | Thời gian tới event tương lai gần nhất |

## Kết quả

Tỷ lệ fraud trong test là `0.034077`, được dùng làm baseline ngẫu nhiên cho PR-AUC.

| Dataset | Số feature | ROC-AUC | PR-AUC | PR-AUC lift |
|---|---:|---:|---:|---:|
| PIT | 4 | 0.679783 | 0.067894 | 1.992x |
| Future-only | 4 | 0.674214 | 0.064931 | 1.905x |
| PIT + future | 8 | 0.705485 | 0.074536 | 2.187x |

## Phân tích

Phép thử kiểm soát là so sánh `pit_plus_future` với `pit`: ROC-AUC cao hơn +0.025702 và PR-AUC cao hơn +0.006641. Khác biệt duy nhất là model thứ hai nhận thêm future feature.

Phép thử theo đặc tả là so sánh `future_only` với `pit`: ROC-AUC thấp hơn -0.005569 và PR-AUC thấp hơn -0.002963. Phép thử này đồng thời thay tín hiệu quá khứ bằng tín hiệu tương lai nên chỉ được xem là kết quả phụ.

Kết luận chỉ mô tả kết quả thực nghiệm; không giả định trước rằng thông tin tương lai luôn làm metric tăng.
