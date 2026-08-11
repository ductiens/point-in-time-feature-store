# Point-in-Time Correct Feature Store

Feature store tối giản cho bộ dữ liệu [IEEE-CIS Fraud Detection](https://www.kaggle.com/c/ieee-fraud-detection), tập trung vào tính đúng tại thời điểm dự đoán (point-in-time correctness). Dự án dùng DuckDB cho offline store và chứng minh rolling feature không sử dụng giao dịch hiện tại hoặc dữ liệu tương lai.

> Trạng thái hiện tại: warehouse, feature catalog, offline engine, leakage experiment và backfill đã hoàn thành. Redis/FastAPI online engine, offline-online parity và monitoring chưa được triển khai.

## Mục tiêu

- Tính feature theo khoảng `[cutoff - window, cutoff)`: bao gồm biên dưới và loại trừ đúng cutoff.
- Sinh feature từ catalog YAML thay vì hard-code tên và cửa sổ ở nhiều nơi.
- So sánh PIT-correct feature với future-looking feature bằng temporal split.
- Kiểm chứng các biên thời gian và kết quả tính toán bằng test tự động.

## Workflow

```text
Raw data
    ↓
01_eda_and_entity_selection.ipynb
    ↓
Warehouse
    ↓
Feature catalog
    ↓
Offline PIT features
    ↓
02_leakage_experiment.ipynb
    ↓
Backfill
```

Hai notebook là nơi trình bày EDA, visualization, research reasoning, baseline,
model comparison và evaluation. `src/pit_feature_store/` giữ logic dữ liệu có thể
tái sử dụng như validation, warehouse, catalog, PIT/future feature calculation và
chuẩn bị modeling dataset; `leakage.py` không chứa code train/evaluate model hoặc
research report.

Pseudo-entity đang dùng là `card1 + card2 + addr1`, được chọn từ kết quả thực nghiệm: độ phủ 87,45%, 60,49% entity có từ hai giao dịch và 97,15% dòng có UID thuộc entity lặp lại.

## Feature catalog

Catalog tại `config/feature_catalog.yaml` định nghĩa bốn feature:

| Feature                   | Phép tổng hợp     |  Cửa sổ | Giá trị khi không có lịch sử |
| ------------------------- | ----------------- | ------: | ---------------------------: |
| `sum_amt_24h`             | `sum`             |  24 giờ |                          `0` |
| `count_txn_24h`           | `count`           |  24 giờ |                          `0` |
| `sum_amt_7d`              | `sum`             | 168 giờ |                          `0` |
| `time_since_last_txn_sec` | `time_since_last` | 720 giờ |                       `NULL` |

Mọi rolling feature dùng cùng time semantics:

```text
[cutoff - window, cutoff)
```

Vì vậy, event tại đúng `cutoff - window` được tính; event tại đúng `cutoff` và mọi event tương lai bị loại.

## Yêu cầu môi trường

- Python 3.11 trở lên (đã xác minh với Python 3.13.7).
- Windows PowerShell cho các lệnh bên dưới.
- Tài khoản Kaggle đã chấp nhận điều khoản cuộc thi IEEE-CIS nếu tải dữ liệu bằng Kaggle CLI.
- Khoảng trống đĩa đủ cho CSV gốc, DuckDB warehouse và notebook output.

Redis không cần thiết ở trạng thái hiện tại vì online engine chưa được triển khai.

## Cài đặt từ môi trường mới

Chạy từ thư mục gốc của repository:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

Kiểm tra package và các dependency chính:

```powershell
python -c "import duckdb, pandas, pyarrow, sklearn, lightgbm; import pit_feature_store; print(pit_feature_store.__file__)"
```

## Chuẩn bị dữ liệu

Pipeline chính cần `train_transaction.csv`; integration test hiện tại cũng kiểm tra `train_identity.csv`. Đặt hai file tại:

```text
data/raw/ieee/train_transaction.csv
data/raw/ieee/train_identity.csv
```

Có thể tải bằng Kaggle CLI sau khi cấu hình thông tin xác thực và chấp nhận điều khoản cuộc thi:

```powershell
New-Item -ItemType Directory -Force data/raw/ieee
kaggle competitions download -c ieee-fraud-detection -p data/raw/ieee
Expand-Archive -Path data/raw/ieee/ieee-fraud-detection.zip -DestinationPath data/raw/ieee -Force
```

Dữ liệu raw được Git ignore và không được commit. Warehouse yêu cầu đúng 590.540 dòng cùng các cột `TransactionID`, `TransactionDT`, `TransactionAmt`, `isFraud`, `card1`, `card2` và `addr1`.

## Chạy pipeline hiện có

Các lệnh dưới đây phải chạy từ thư mục gốc repository và theo đúng thứ tự.

### 1. Chạy EDA và chọn pseudo-entity

```powershell
python -m jupyter nbconvert --to notebook --execute notebooks/01_eda_and_entity_selection.ipynb --output-dir artifacts/reports --output 01_eda_and_entity_selection.executed.ipynb --ExecutePreprocessor.timeout=900
```

Notebook quét trực tiếp `train_transaction.csv`, trình bày statistics, missing/data
quality, fraud label, amount/temporal visualization và reasoning chọn UID. Module
`pit_feature_store.entity_selection` chỉ tính metrics dùng chung; notebook quyết
định candidate và tạo `artifacts/reports/entity_candidate_results.csv`.

### 2. Khởi tạo DuckDB warehouse

```powershell
python scripts/init_warehouse.py
```

Lệnh tạo lại bảng `transactions` tại `artifacts/warehouse.duckdb`, chuẩn hóa thời gian theo:

```text
event_ts = 2017-12-01 00:00:00 + TransactionDT giây
```

Kiểm tra nhanh số dòng:

```powershell
python -c "import duckdb; con=duckdb.connect('artifacts/warehouse.duckdb', read_only=True); print(con.sql('SELECT COUNT(*) FROM transactions').fetchone()[0]); con.close()"
```

Kết quả mong đợi: `590540`.

### 3. Validate catalog và tạo offline feature

```powershell
python -m pit_feature_store.catalog
python -m pit_feature_store.offline_engine
```

Offline engine tạo trong DuckDB:

- `label_spine`: điểm dự đoán và label.
- `feature_events`: lịch sử event, không chứa label.
- `feature_cumsum`: cumulative sum/count theo UID.
- `pit_features`: bốn feature PIT-correct cho 590.540 giao dịch.

### 4. Chạy leakage experiment

```powershell
python -m jupyter nbconvert --to notebook --execute notebooks/02_leakage_experiment.ipynb --output-dir artifacts/reports --output 02_leakage_experiment.executed.ipynb --ExecutePreprocessor.timeout=900
```

Notebook hiển thị feature distributions, temporal split, Dummy baseline và code
train/evaluate trực tiếp cho PIT, future-only, PIT + future LightGBM. Notebook ghi:

- `artifacts/reports/leakage_metrics.csv`
- `artifacts/reports/leakage_experiment.md`
- `artifacts/reports/02_leakage_experiment.executed.ipynb`

Kết quả đã xác minh trên môi trường dự án:

| Model        |  ROC-AUC |   PR-AUC |
| ------------ | -------: | -------: |
| Dummy prior  | 0,500000 | 0,034077 |
| PIT          | 0,679783 | 0,067894 |
| Future-only  | 0,674214 | 0,064931 |
| PIT + future | 0,705485 | 0,074536 |

Future-only không mặc định tốt hơn PIT; kết luận leakage dựa trên số liệu thực nghiệm. Phép so sánh kiểm soát `PIT + future` cao hơn PIT ở lần chạy đã xác minh.

### 5. Chạy backfill

```powershell
python scripts/run_backfill.py --start-date 2018-01-01 --end-date 2018-01-01
```

Khoảng ngày bao gồm cả `start-date` và `end-date`. Backfill tự lấy lookback lớn
nhất từ catalog, dùng TEMP objects và ghi kết quả an toàn tại:

```text
artifacts/offline_store/backfill/version=<catalog-version>-<fingerprint>/<start>_<end>/features.parquet
```

Catalog snapshot nằm cạnh Parquet; log mỗi lần chạy nằm tại
`artifacts/logs/backfill_log.jsonl`.

## Chạy test

Unit test không cần dataset Kaggle hoặc service ngoài:

```powershell
python -m pytest tests/unit -v
```

Toàn bộ test:

```powershell
python -m pytest tests -v
```

Integration test Stage 1 yêu cầu raw data và warehouse thật; các test backfill dùng
warehouse nhỏ tự tạo. Test hiện tại bao phủ catalog validation, PIT boundaries,
temporal split, backfill idempotency và backfill/full-pipeline equality.

## Cấu trúc repository

```text
.
├── config/
│   └── feature_catalog.yaml
├── data/raw/ieee/                 # Git ignored
├── notebooks/
│   ├── 01_eda_and_entity_selection.ipynb
│   └── 02_leakage_experiment.ipynb
├── scripts/
│   ├── init_warehouse.py
│   └── run_backfill.py
├── src/pit_feature_store/
│   ├── backfill.py
│   ├── catalog.py
│   ├── entity_selection.py
│   ├── leakage.py
│   ├── offline_engine.py
│   └── warehouse.py
├── tests/
│   ├── integration/
│   └── unit/
├── artifacts/                     # Git ignored
├── pyproject.toml
└── requirements.txt
```

`artifacts/` chứa warehouse, report và notebook đã execute; toàn bộ thư mục này được tạo lại và không được commit.

## Giới hạn hiện tại

- UID là pseudo-entity, không phải customer ID thật; các giao dịch thiếu `card1`, `card2` hoặc `addr1` không có UID.
- Chưa có Redis replay, virtual clock, FastAPI serving hoặc offline-online parity.
- Integration test vẫn phụ thuộc full Kaggle dataset và artifact được tạo trước.
- Các path runtime là path tương đối, vì vậy cần chạy lệnh từ thư mục gốc repository.
