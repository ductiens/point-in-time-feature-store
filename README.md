# Point-in-Time Correct Feature Store

Feature store tối giản cho bộ dữ liệu [IEEE-CIS Fraud Detection](https://www.kaggle.com/c/ieee-fraud-detection), tập trung vào tính đúng tại thời điểm dự đoán (point-in-time correctness). Dự án dùng DuckDB cho offline store và chứng minh rolling feature không sử dụng giao dịch hiện tại hoặc dữ liệu tương lai.

> Trạng thái hiện tại: warehouse, feature catalog, offline engine, leakage
> experiment, backfill và Redis/FastAPI online engine đã hoàn thành.
> Offline-online parity và monitoring chưa được triển khai.

## Mục tiêu

- Tính feature theo khoảng `[cutoff - window, cutoff)`: bao gồm biên dưới và loại trừ đúng cutoff.
- Sinh feature từ catalog YAML thay vì hard-code tên và cửa sổ ở nhiều nơi.
- So sánh PIT-correct feature với future-looking feature bằng temporal split.
- Replay raw event vào Redis và phục vụ cùng feature catalog qua FastAPI.
- Kiểm chứng các biên thời gian và kết quả tính toán bằng test tự động.

## Workflow

```text
Raw data
    ↓
01_eda_and_entity_selection.ipynb
    ↓
Warehouse + Feature catalog
    ├── Offline PIT features
    │       ├── 02_leakage_experiment.ipynb
    │       └── Versioned backfill
    └── Online replay
            ↓
        Redis ZSET raw events + virtual clock
            ↓
        FastAPI GET /features/{uid}
```

Hai notebook là nơi trình bày EDA, visualization, research reasoning, baseline,
model comparison và evaluation. `src/pit_feature_store/` giữ logic dữ liệu có thể
tái sử dụng như validation, warehouse, catalog, PIT/future feature calculation và
chuẩn bị modeling dataset; `leakage.py` không chứa code train/evaluate model hoặc
research report.

`online_engine.py` đọc cùng feature catalog, tự tính feature từ raw Redis event
và không copy feature đã tính từ DuckDB. Replay luôn compute trước khi ingest
transaction hiện tại; `serving.py` dùng virtual clock của dataset nếu request
không truyền cutoff.

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
- Docker Desktop hoặc một Redis server tương thích để chạy replay/API thật.
- Tài khoản Kaggle đã chấp nhận điều khoản cuộc thi IEEE-CIS nếu tải dữ liệu bằng Kaggle CLI.
- Khoảng trống đĩa đủ cho CSV gốc, DuckDB warehouse và notebook output.

Unit/integration test Giai đoạn 6 dùng `fakeredis`, vì vậy chạy test không bắt
buộc Docker hoặc Redis server thật.

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
python -c "import duckdb, pandas, pyarrow, sklearn, lightgbm, redis, fastapi, fakeredis; import pit_feature_store; print(pit_feature_store.__file__)"
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

```powershell
python -c "import pandas as pd, hashlib; p='artifacts/offline_store/backfill/version=1.0.0-a56eaf7727288928/2018-01-01_2018-01-01/features.parquet'; df=pd.read_parquet(p).sort_values(['cutoff_ts','label_id']).reset_index(drop=True); csv=df.to_csv(index=False, lineterminator='\n', date_format='%Y-%m-%d %H:%M:%S.%f', na_rep='<NA>', float_format='%.17g'); print('rows=', len(df)); print('logic_sha256=', hashlib.sha256(csv.encode('utf-8')).hexdigest())"
```

Khoảng ngày bao gồm cả `start-date` và `end-date`. Backfill tự lấy lookback lớn
nhất từ catalog, dùng TEMP objects và ghi kết quả an toàn tại:

```text
artifacts/offline_store/backfill/version=<catalog-version>-<fingerprint>/<start>_<end>/features.parquet
```

Catalog snapshot nằm cạnh Parquet; log mỗi lần chạy nằm tại
`artifacts/logs/backfill_log.jsonl`.

### 6. Khởi động Redis và chạy online replay

Hướng dẫn Docker, kiểm tra Redis, gọi API và troubleshooting đầy đủ nằm tại
[STAGE6_ONLINE_ENGINE_API.md](STAGE6_ONLINE_ENGINE_API.md).

Quick start cho local development:

```powershell
docker pull redis:8.8.0-alpine
docker run --name pit-redis --detach --publish 127.0.0.1:6379:6379 redis:8.8.0-alpine
docker exec pit-redis redis-cli ping

$env:REDIS_URL = "redis://127.0.0.1:6379/0"
python scripts/run_online_replay.py
```

Replay đọc `transactions` theo `event_ts, transaction_id`, xóa riêng
`events:*` và `sys:virtual_now_epoch`, tính feature trước khi ingest rồi cập
nhật virtual clock. Key không thuộc dự án không bị xóa.

Kiểm tra clock sau replay:

```powershell
docker exec pit-redis redis-cli GET sys:virtual_now_epoch
```

### 7. Chạy serving API

Mở PowerShell thứ hai tại repository:

```powershell
$env:REDIS_URL = "redis://127.0.0.1:6379/0"
python scripts/run_api.py
```

Swagger UI: <http://127.0.0.1:8000/docs>

Endpoint:

```text
GET /features/{uid}
GET /features/{uid}?as_of_epoch=<epoch>
```

Nếu bỏ `as_of_epoch`, API dùng `sys:virtual_now_epoch`; nếu clock chưa tồn tại,
API trả HTTP 503. Response chứa trực tiếp đủ bốn feature trong catalog.

## Chạy test

Unit test và test API Giai đoạn 6 không cần Redis server thật:

```powershell
python -m pytest tests/unit -v
```

Chạy riêng Giai đoạn 6:

```powershell
python -m pytest tests/unit/test_online_engine.py tests/integration/test_online_replay.py tests/integration/test_serving_api.py -v
```

Toàn bộ test:

```powershell
python -m pytest tests -v
```

Integration test Stage 1 yêu cầu raw data và warehouse thật; các test backfill dùng
warehouse nhỏ tự tạo. Test hiện tại bao phủ catalog validation, PIT boundaries,
temporal split, backfill idempotency, backfill/full-pipeline equality, Redis
online semantics, deterministic replay và FastAPI virtual-clock behavior.

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
│   ├── run_backfill.py
│   ├── run_online_replay.py
│   └── run_api.py
├── src/pit_feature_store/
│   ├── backfill.py
│   ├── catalog.py
│   ├── entity_selection.py
│   ├── leakage.py
│   ├── offline_engine.py
│   ├── online_engine.py
│   ├── serving.py
│   └── warehouse.py
├── tests/
│   ├── integration/
│   └── unit/
├── artifacts/                     # Git ignored
├── STAGE6_ONLINE_ENGINE_API.md
├── pyproject.toml
└── requirements.txt
```

`artifacts/` chứa warehouse, report và notebook đã execute; toàn bộ thư mục này được tạo lại và không được commit.

## Giới hạn hiện tại

- UID là pseudo-entity, không phải customer ID thật; các giao dịch thiếu `card1`, `card2` hoặc `addr1` không có UID.
- Chưa có offline-online parity; nội dung này thuộc Giai đoạn 7.
- Chưa benchmark replay toàn bộ 590.540 transaction hoặc API với Redis server thật.
- Integration test vẫn phụ thuộc full Kaggle dataset và artifact được tạo trước.
- Các path runtime là path tương đối, vì vậy cần chạy lệnh từ thư mục gốc repository.
