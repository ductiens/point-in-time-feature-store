# PROJECT SPECIFICATION

## 1. Tên dự án

Point-in-Time Correct Feature Store for Fraud Detection.

## 2. Bài toán

Xây dựng một feature store tối giản nhằm bảo đảm:

- Feature dùng để training chỉ chứa dữ liệu đã tồn tại tại thời điểm dự đoán.
- Feature tại offline training và online serving có cùng ý nghĩa.
- Không xảy ra target leakage.
- Có thể backfill lại feature lịch sử.
- Kết quả backfill có thể tái lập.
- Offline engine và online engine có thể kiểm tra parity.

## 3. Câu hỏi nghiên cứu

1. Làm thế nào tạo feature lịch sử mà không sử dụng dữ liệu tương lai?
2. Point-in-Time Join có giúp tránh data leakage hay không?
3. Kết quả model thay đổi như thế nào giữa dữ liệu leaky và dữ liệu PIT-correct?
4. Backfill có thể chạy lại và tạo ra cùng kết quả hay không?
5. Offline engine và online engine có cho cùng feature tại cùng entity và cutoff hay không?

## 4. Phạm vi dữ liệu

Dataset chính:

- IEEE-CIS Fraud Detection.
- File chính: `data/raw/ieee/train_transaction.csv`.
- File bổ sung: `data/raw/ieee/train_identity.csv`.
- Số giao dịch mong đợi: 590.540.
- Nhãn: `isFraud`.
- Thời gian tương đối: `TransactionDT`.
- Giá trị giao dịch: `TransactionAmt`.

Pipeline chính chỉ bắt buộc sử dụng `train_transaction.csv`.

`train_identity.csv` được giữ lại để mở rộng nhưng không bắt buộc tham gia pipeline chính.

## 5. Pseudo-entity

Dataset không có customer ID thật.

Phải đánh giá ít nhất ba candidate:

1. `card1 + addr1`
2. `card1 + card2 + addr1`
3. `card1 + card2 + addr1 + D1`

Mỗi candidate cần có:

- Số lượng entity.
- Tỷ lệ entity có ít nhất hai giao dịch.
- Số giao dịch lớn nhất trên một entity.
- Số giao dịch trung bình hoặc trung vị trên entity nếu phù hợp.

Kết quả lưu tại:

`artifacts/reports/entity_candidate_results.csv`

Candidate cuối cùng phải được chọn dựa trên kết quả thực nghiệm, không được chọn tùy ý.

Công thức cuối cùng phải được sử dụng nhất quán trong bước khởi tạo warehouse.

> Kết quả thực tế (xem `STATUS.md` mục 5): candidate đã chọn là `card1 + card2 + addr1` — độ phủ 87,45%, tỷ lệ entity lặp 60,49%, tỷ lệ dòng thuộc entity lặp 97,15%.

Notebook `01_eda_and_entity_selection.ipynb` là báo cáo EDA chính: phải đọc raw
transaction trực tiếp, trình bày overview/schema/statistics, missing values, data
quality, fraud-label imbalance, amount/temporal visualization và candidate
comparison. Module `entity_selection.py` chỉ tính/export metrics dùng chung; quyết
định candidate và reasoning nằm trong notebook, không phụ thuộc threshold tùy ý.

## 6. Chuẩn hoá thời gian

Chuyển `TransactionDT` thành:

`event_ts = 2017-12-01 00:00:00 + TransactionDT giây`

Đây là timestamp giả lập.

Tất cả thành phần offline, online, backfill, API và monitoring phải sử dụng cùng quy ước này.

## 7. Bảng transactions

Warehouse phải có bảng `transactions` với tối thiểu các cột:

| Cột | Ý nghĩa |
|---|---|
| `transaction_id` | ID giao dịch |
| `uid` | Pseudo-entity đã hash |
| `event_ts` | Timestamp đã chuẩn hoá |
| `amount` | Giá trị giao dịch |
| `label` | Nhãn fraud |

Có thể giữ tên cột gốc như `TransactionID`, `TransactionAmt`, `isFraud` nếu source hiện tại đã dùng nhất quán, nhưng các engine phía sau phải sử dụng thống nhất.

Số dòng mong đợi:

`590540`

## 8. Feature catalog

Tạo file `feature_catalog.yaml` với bốn feature:

| Feature | Aggregation | Window |
|---|---|---:|
| `sum_amt_24h` | `sum` | 24 giờ |
| `count_txn_24h` | `count` | 24 giờ |
| `sum_amt_7d` | `sum` | 168 giờ |
| `time_since_last_txn_sec` | `time_since_last` | 720 giờ |

`time_since_last_txn_sec` trả về `NULL` hoặc `None` nếu không có giao dịch trước đó trong 720 giờ.

## 9. Time semantics

Tất cả rolling feature phải dùng:

`[cutoff - window, cutoff)`

Ví dụ feature 24 giờ tại thời điểm `2020-01-02 10:00`:

- Bao gồm event tại `2020-01-01 10:00`.
- Bao gồm event sau thời điểm đó.
- Không bao gồm event tại `2020-01-02 10:00`.
- Không bao gồm event sau cutoff.

## 10. Offline pipeline

Offline pipeline sử dụng DuckDB.

Phải có:

1. `label_spine`
2. `feature_events`
3. `feature_cumsum`
4. `pit_features`

### label_spine

Chứa: `label_id`, `uid`, `cutoff_ts`, `label`. Không chứa feature.

### feature_events

Chứa: `uid`, `feature_ts`, `amount`, `event_id`. Không chứa label.

### feature_cumsum

Chứa cumulative sum và cumulative count theo từng entity.

### pit_features

Chứa: `label_id`, `uid`, `cutoff_ts`, `label`, bốn feature từ catalog.

Window feature được tính bằng cumulative value tại cutoff trừ cumulative value trước biên dưới window.

## 11. Leakage experiment

Phải tạo hai bộ dữ liệu:

### PIT-correct

Chỉ sử dụng lịch sử trước cutoff.

### Leaky

Sử dụng dữ liệu tương lai có chủ đích:

- `(cutoff, cutoff + 24h]`
- `(cutoff, cutoff + 7d]`

Hai bộ dữ liệu phải dùng cùng tên feature và cùng độ dài window.

Model:

- Dummy baseline trên cùng temporal split.
- LightGBM classifier.
- Train/test split theo thời gian.
- Không random split.
- Feature thiếu được xử lý nhất quán.

Metric:

- ROC-AUC.
- PR-AUC.

Kết quả phải được ghi lại để phân tích. Không bắt buộc metric leaky phải cao hơn; kết luận phải dựa trên kết quả thực tế.

> **Cách trình bày (bổ sung):** feature exploration, temporal split, baseline,
> khởi tạo/fit/predict model, so sánh metric, visualization và phân tích phải nhìn
> thấy trực tiếp trong `notebooks/02_leakage_experiment.ipynb`. Module `.py` giữ
> SQL/PIT/future dataset preparation và validation dùng chung; notebook không được
> chỉ gọi một hàm `run_experiment()` che toàn bộ research flow. `leakage.py` không
> chứa LightGBM training, metric evaluation, experiment orchestration hoặc research
> report.

## 12. Backfill

Backfill phải:

- Nhận `start_date`.
- Nhận `end_date`.
- Đọc dữ liệu từ bảng `transactions`.
- Tự tính lookback từ catalog.
- Sử dụng TEMP view/table.
- Không ghi đè `pit_features` chính.
- Tạo catalog fingerprint.
- Ghi output theo version.
- Lưu catalog snapshot.
- Ghi Parquet bằng file tạm rồi replace.
- Ghi log lần chạy.
- Chạy lại cùng input cho cùng dữ liệu logic.

Output dạng:

`artifacts/offline_store/backfill/version=<version>/<start>_<end>/features.parquet`

## 13. Online pipeline

Online pipeline sử dụng Redis ZSET.

Redis key: `events:<uid>`

ZSET: member chứa transaction ID và amount; score chứa timestamp epoch.

Online engine phải có: `ingest_event()`, `compute_features()`.

Online engine phải đọc `feature_catalog.yaml`.

Không được đọc hoặc copy feature từ `pit_features`.

## 14. Replay và virtual clock

Replay phải:

1. Xoá state Redis cũ của dự án.
2. Đọc transaction theo thứ tự thời gian.
3. Tính feature trước khi ingest event hiện tại.
4. Ingest event.
5. Cập nhật `sys:virtual_now_epoch`.

Replay phải deterministic.

## 15. Serving API

FastAPI endpoint: `GET /features/{uid}`

Có thể nhận `as_of_epoch`.

Nếu không truyền `as_of_epoch`:

- Sử dụng `sys:virtual_now_epoch`.
- Nếu virtual clock chưa tồn tại, trả HTTP 503.

Response phải có đủ bốn feature.

## 16. Parity test

Parity test so sánh offline và online tại cùng `uid` và `cutoff`.

Yêu cầu:

- Ít nhất 50 mẫu.
- So đủ bốn feature.
- Chuẩn hoá `NULL`, `NaN` và `None`.
- Chấp nhận sai số float nhỏ.
- Chỉ một bên missing được coi là mismatch.
- Kết quả hoàn thành khi mismatch bằng 0.

## 17. Test bắt buộc

Phải có tối thiểu:

- Test feature catalog.
- Test offline calculation so với Pandas.
- Test biên thời gian.
- Test backfill idempotency.
- Test backfill khớp full offline pipeline trên cùng khoảng.
- Test online engine.
- Test API trả 503 khi thiếu virtual clock.
- Test offline-online parity.

> **Nguyên tắc phân loại test (bổ sung):** `tests/unit/` = test 1 component độc lập, ưu tiên dùng fixture nhỏ tự tạo trong test (DuckDB in-memory, `fakeredis`) thay vì phụ thuộc dataset Kaggle thật hoặc Redis thật — để chạy được trên CI không cần secret/service ngoài. `tests/integration/` = test nhiều component nối nhau (CLI thật, warehouse thật, API thật qua `TestClient`). Ranh giới là **phạm vi test**, không phải "có cần data thật hay không" — cả hai tầng đều nên tránh phụ thuộc dataset Kaggle thật khi có thể.

## 18. Công nghệ

- Python
- DuckDB
- Pandas
- PyArrow
- PyYAML
- Pydantic
- LightGBM
- Scikit-learn
- Redis
- FastAPI
- Uvicorn
- Click
- Pytest
- `fakeredis` (test online engine/API không cần Redis thật)
- `httpx` (bắt buộc cho FastAPI `TestClient`)
- Cấu trúc package chuẩn (`pyproject.toml`, `pip install -e .`) — xem mục 21

## 19. Ngoài phạm vi

Không bắt buộc: Kafka, Redpanda, Spark, Feast, Airflow, Kubernetes, Cloud deployment, PaySim, Home Credit, Authentication cho API, Production-scale performance.

Không được tự bổ sung các công nghệ trên nếu chưa có yêu cầu rõ ràng.

## 20. Điều kiện hoàn thành toàn dự án

Dự án hoàn thành khi:

1. Warehouse có đủ dữ liệu.
2. Feature catalog validate thành công.
3. Offline pipeline tạo đủ bốn feature.
4. Offline correctness tests pass.
5. Leakage experiment tạo ROC-AUC và PR-AUC.
6. Backfill idempotency test pass.
7. Backfill khớp full offline pipeline.
8. Online engine hoạt động.
9. API trả đủ feature.
10. Parity test có 0 mismatch.
11. Toàn bộ pytest pass.
12. README hướng dẫn chạy lại từ môi trường sạch.
13. Proposal và báo cáo cuối được hoàn thiện.
14. Cấu trúc mã nguồn khớp mục 21 (không còn file `.py` nghiên cứu/report model ở root).

## 21. Cấu trúc mã nguồn

Áp dụng từ Giai đoạn 5 trở đi (xem `TODO.md` Giai đoạn 4.5 — migration). Giai đoạn 1-4 đã hoàn thành dưới cấu trúc flat cũ (mọi `.py` ở root) trước khi quy ước này được duyệt; được di dời cơ học (đổi vị trí + sửa import, KHÔNG đổi logic/kết quả) trong Giai đoạn 4.5.

```
pit-feature-store/
├── pyproject.toml, requirements.txt, .gitignore, .env.example
├── config/
│   ├── feature_catalog.yaml
│   └── settings.yaml
├── src/pit_feature_store/
│   ├── __init__.py, config.py, logging_config.py
│   ├── catalog.py, entity_selection.py, warehouse.py, offline_engine.py, backfill.py
│   ├── online_engine.py, serving.py, parity.py, leakage.py
│   └── monitoring/ (freshness.py, psi.py)
├── scripts/                # CLI mỏng, chỉ gọi lại src/
│   ├── init_warehouse.py, run_offline.py, run_backfill.py
│   ├── run_online_replay.py, run_api.py, run_parity.py, run_monitoring.py
├── notebooks/
│   ├── 01_eda_and_entity_selection.ipynb   (thay evaluate_entity_candidates.py)
│   └── 02_leakage_experiment.ipynb         (thay leakage_experiment.py — nơi DUY NHẤT report model)
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/
├── data/raw/ieee/
└── artifacts/               # 🚫 gitignored — warehouse.duckdb, reports/, offline_store/, logs/
```

**Bảng ánh xạ file cũ (Giai đoạn 1-4) → file mới:**

| File cũ (root) | File mới |
|---|---|
| `catalog.py` | `src/pit_feature_store/catalog.py` |
| `offline_engine.py` | `src/pit_feature_store/offline_engine.py` |
| `init_warehouse.py` | `src/pit_feature_store/warehouse.py` (logic) + `scripts/init_warehouse.py` (CLI) |
| `evaluate_entity_candidates.py` | `src/pit_feature_store/entity_selection.py` (logic) + `notebooks/01_eda_and_entity_selection.ipynb` (phân tích/report) |
| `leakage_experiment.py` | `src/pit_feature_store/leakage.py` (logic) + `notebooks/02_leakage_experiment.ipynb` (report) |
| `feature_catalog.yaml` | `config/feature_catalog.yaml` |
| `warehouse.duckdb` | `artifacts/warehouse.duckdb` |
| `reports/*.csv`, `reports/*.md` | `artifacts/reports/*.csv`, `artifacts/reports/*.md` |
| `offline_store/` | `artifacts/offline_store/` |

Mọi mục ở phần 6-17 phía trên dùng tên file ngắn gọn (ví dụ "backfill.py phải...") — hiểu theo bảng ánh xạ trên, trừ khi ghi chú khác.
