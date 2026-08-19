# PROJECT STATUS

Cập nhật lần cuối: 2026-08-14, đã được Codex xác minh sau khi hoàn thành
Giai đoạn 7 — Parity.

## 1. Giai đoạn hiện tại

Dự án đã hoàn thành Giai đoạn 7: Parity.

Giai đoạn 4.5 đã hoàn thành toàn bộ 7 sub-task từ 4.5.1 đến 4.5.7; Giai đoạn 5
đã hoàn thành toàn bộ 4 sub-task từ 5.1 đến 5.4; Giai đoạn 6 đã hoàn thành toàn
bộ 4 sub-task từ 6.1 đến 6.4; Giai đoạn 7 đã hoàn thành cả 7.1 và 7.2.

README đã được cập nhật theo src-layout và mô tả workflow tái lập hiện có từ cài
đặt, chuẩn bị dữ liệu, đánh giá pseudo-entity, warehouse/offline feature, leakage
experiment, backfill đến Redis replay và FastAPI. Hướng dẫn Docker/API chi tiết
nằm tại `STAGE6_ONLINE_ENGINE_API.md`. Task 10.2 vẫn chờ bổ sung workflow parity
vào README và lượt kiểm tra tài liệu end-to-end từ môi trường sạch.

Notebook EDA hiện import logic từ `src/pit_feature_store/entity_selection.py`,
quét trực tiếp `train_transaction.csv` và tự ghi report; không còn đọc
`artifacts/reports/entity_candidate_results.csv` làm nguồn dữ liệu.

Notebook 01 hiện là EDA report đầy đủ. Notebook 02 trực tiếp hiển thị feature
exploration, temporal split, Dummy baseline và ba LightGBM fit/evaluation; reusable
SQL/PIT/future dataset preparation vẫn ở `src/pit_feature_store/`. Notebook 02
cũng có controlled leakage evidence: prediction-time timeline, held-out permutation
importance, grouped future-block shuffle và paired bootstrap uncertainty.

**Quyết định mới (2026-08-07):** đã duyệt cấu trúc mã nguồn dạng src-layout (`src/pit_feature_store/`, `scripts/`, `notebooks/`, `tests/unit`+`integration`, `artifacts/`) — xem `PROJECT_SPEC.md` mục 21 và `TODO.md` Giai đoạn 4.5. Giai đoạn 1-4 đã hoàn thành dưới cấu trúc flat cũ (root), **không viết lại logic/kết quả đã có** — chỉ cần 1 lượt di dời cơ học (Giai đoạn 4.5) trước khi tiếp tục Giai đoạn 5.

## 2. File đang có

### Dữ liệu

- `data/raw/ieee/train_transaction.csv`
- `data/raw/ieee/train_identity.csv`

### Source code còn ở cấu trúc flat cũ

- Không còn các file flat chính thức trong bảng ánh xạ Giai đoạn 1-4 của
  `PROJECT_SPEC.md` mục 21.
- Không còn `uid.py` hoặc wrapper entity-selection ở root.

### Source code đã chuyển sang src-layout

- `src/pit_feature_store/catalog.py`
- `src/pit_feature_store/entity_selection.py`
- `src/pit_feature_store/offline_engine.py`
- `src/pit_feature_store/warehouse.py`
- `src/pit_feature_store/leakage.py`
- `src/pit_feature_store/backfill.py`
- `src/pit_feature_store/online_engine.py`
- `src/pit_feature_store/serving.py`
- `src/pit_feature_store/parity.py`
- `scripts/init_warehouse.py`
- `scripts/run_backfill.py`
- `scripts/run_online_replay.py`
- `scripts/run_api.py`
- `scripts/run_parity.py`
- `notebooks/01_eda_and_entity_selection.ipynb`
- `notebooks/02_leakage_experiment.ipynb`

### Output

- `artifacts/warehouse.duckdb`
- `artifacts/reports/entity_candidate_results.csv`
- `artifacts/reports/leakage_metrics.csv`
- `artifacts/reports/leakage_experiment.md`
- `artifacts/reports/02_leakage_experiment.executed.ipynb`
- `artifacts/offline_store/backfill/version=1.0.0-a56eaf7727288928/2018-01-01_2018-01-01/features.parquet`
- `artifacts/offline_store/backfill/version=1.0.0-a56eaf7727288928/2018-01-01_2018-01-01/catalog_snapshot.yaml`
- `artifacts/logs/backfill_log.jsonl`

### Cấu hình

- `.env`
- `.env.example`
- `.gitignore`
- `config/feature_catalog.yaml`
- `pyproject.toml`
- `requirements.txt`

### Tài liệu

- `README.md`
- `STAGE6_ONLINE_ENGINE_API.md`

### Thư mục đã tạo

- `tests/`
- `monitoring/`
- `artifacts/`
- `config/`
- `scripts/`
- `notebooks/`
- `src/pit_feature_store/`
- `tests/unit/`
- `tests/integration/`

## 3. File đã kiểm tra

- `README.md`
- `STAGE6_ONLINE_ENGINE_API.md`
- `requirements.txt`
- `notebooks/01_eda_and_entity_selection.ipynb`
- `artifacts/reports/entity_candidate_results.csv`
- `src/pit_feature_store/warehouse.py`
- `scripts/init_warehouse.py`
- `reports/entity_candidate_results.csv` (kiểm tra trước khi xóa legacy)
- `data/raw/ieee/train_transaction.csv` (chỉ đọc)
- `data/raw/ieee/train_identity.csv` (chỉ kiểm tra tồn tại)
- `warehouse.duckdb` (kiểm tra trước khi xóa legacy)
- `artifacts/warehouse.duckdb`
- `tests/integration/test_stage1.py`
- `config/feature_catalog.yaml`
- `src/pit_feature_store/catalog.py`
- `src/pit_feature_store/offline_engine.py`
- `tests/conftest.py`
- `tests/unit/test_catalog.py`
- `tests/unit/test_entity_selection.py`
- `tests/unit/test_offline_correctness.py`
- `tests/unit/test_time_boundaries.py`
- `tests/unit/test_leakage_experiment.py`
- `src/pit_feature_store/leakage.py`
- `notebooks/02_leakage_experiment.ipynb`
- `artifacts/reports/leakage_metrics.csv`
- `artifacts/reports/leakage_experiment.md`
- `src/pit_feature_store/backfill.py`
- `scripts/run_backfill.py`
- `tests/integration/test_backfill_idempotent.py`
- `tests/integration/test_backfill_matches_full_pipeline.py`
- `src/pit_feature_store/online_engine.py`
- `src/pit_feature_store/serving.py`
- `scripts/run_online_replay.py`
- `scripts/run_api.py`
- `tests/unit/test_online_engine.py`
- `tests/integration/test_online_replay.py`
- `tests/integration/test_serving_api.py`
- `src/pit_feature_store/parity.py`
- `scripts/run_parity.py`
- `tests/unit/test_parity_values.py`
- `tests/integration/test_parity.py`

## 4. File đã sửa

- `pyproject.toml`
  - Khai báo build backend `setuptools` và package discovery theo src-layout.
- `src/pit_feature_store/__init__.py`
  - Khởi tạo package `pit_feature_store`.
- `config/.gitkeep`, `scripts/.gitkeep`, `notebooks/.gitkeep`,
  `tests/unit/.gitkeep`, `tests/integration/.gitkeep`
  - Giữ các thư mục khung rỗng trong Git.
- `notebooks/01_eda_and_entity_selection.ipynb`
  - Query trực tiếp raw CSV bằng DuckDB; không load toàn bộ 394 cột vào pandas.
  - Có overview/schema/statistics, missing analysis, data-quality checks, fraud-label,
    amount/temporal charts và pseudo-entity comparison.
  - Quyết định `card1 + card2 + addr1` được trình bày trong notebook từ metrics vừa
    tính, không phụ thuộc threshold research tùy ý.
- `src/pit_feature_store/entity_selection.py`
  - Chứa candidate definitions, biểu thức UID, validate raw và SQL tính metrics.
  - Chỉ trả/export DataFrame; không còn tự quyết định candidate.
- `tests/unit/test_entity_selection.py`
  - Regression test metrics/export từ CSV raw nhỏ, candidate `D1` bị phân mảnh và
    lỗi thiếu cột; không test research decision của notebook.
- `src/pit_feature_store/warehouse.py`
  - Giữ nguyên logic validate source, tạo/validate bảng `transactions` và in summary.
  - Cung cấp hàm `build_warehouse()`; tự tạo thư mục cha và ghi database tại
    `artifacts/warehouse.duckdb`.
- `scripts/init_warehouse.py`
  - CLI mỏng gọi `build_warehouse()` và in đường dẫn kết quả.
- `tests/integration/test_stage1.py`
  - Đọc report và warehouse thật từ `artifacts/`; giữ nguyên assertion về dataset,
    candidate được chọn và warehouse/UID.
- `config/feature_catalog.yaml`
  - Khai báo version `1.0.0`.
  - Khai báo description, entity, aggregation và source column.
  - Khai báo window, event time, feature version và default value.
- `src/pit_feature_store/catalog.py`
  - Load YAML và validate bằng Pydantic.
  - Giới hạn aggregation/source/default hợp lệ, window nguyên dương.
  - Kiểm tra description, entity, event time và version từng feature.
  - Kiểm tra catalog version, tên SQL-safe, tên duy nhất và YAML rỗng.
  - Tính `max_lookback_hours` từ window lớn nhất.
- `tests/unit/test_catalog.py`
  - Test metadata chuẩn, aggregation/window/source/default sai.
  - Test description, entity, event time và feature version sai.
  - Test catalog version, tên SQL-safe, tên trùng, YAML rỗng và CLI.
- `src/pit_feature_store/offline_engine.py`
  - Tạo riêng `label_spine`, `feature_events` và `feature_cumsum` dưới dạng view.
  - Sinh bảng `pit_features` từ catalog bằng cumulative value và `ASOF JOIN`.
  - Áp dụng cửa sổ `[cutoff-window, cutoff)`, kể cả khi nhiều event cùng timestamp.
  - Hỗ trợ chạy lại an toàn bằng `CREATE OR REPLACE`.
  - Hỗ trợ source relation tùy chọn và TEMP objects cho backfill; hành vi mặc định
    của full offline pipeline giữ nguyên.
  - Default database path chuyển sang `artifacts/warehouse.duckdb`.
- `tests/unit/test_offline_correctness.py`
  - So sánh đủ bốn feature DuckDB với phép tính Pandas thủ công.
  - Kiểm tra schema, loại object, entity độc lập, UID rỗng, timestamp trùng và chạy lại.
  - Kiểm tra tên feature được sinh từ catalog.
- `tests/unit/test_time_boundaries.py`
  - Kiểm tra biên dưới, cutoff, tương lai và gap lớn hơn 24h, 7 ngày, 720h.
- `src/pit_feature_store/leakage.py`
  - Giữ reusable logic tạo `leaky_features`, PIT + future view, observation bounds,
    temporal split và load modeling frames.
  - Đã xóa LightGBM/sklearn imports và các API `train_score_and_evaluate`,
    `train_and_evaluate`, `run_experiment`, `render_report_markdown`; toàn bộ model
    research/report chỉ còn trong notebook 02.
- `notebooks/02_leakage_experiment.ipynb`
  - Chỉ import data-preparation helpers; trực tiếp hiển thị DummyClassifier và code
    khởi tạo/fit/predict/score ba `LGBMClassifier`.
  - Có feature table/distributions, cohort/split summary, comparison table,
    ROC/PR curves, PIT feature importance và conclusion.
  - Phân biệt leakage existence với impact; có timeline transaction thật,
    permutation importance trên test, 50 grouped future-block shuffles, 500 paired
    bootstrap samples, evidence summary và conclusion theo kết quả runtime.
  - Giữ section/chart/report title bằng tiếng Anh; research rationale,
    interpretation, conclusion và report narrative bằng tiếng Việt.
  - Tạo `artifacts/reports/leakage_metrics.csv` và
    `artifacts/reports/leakage_experiment.md`; Markdown report chứa controlled
    delta, bootstrap CI, shuffle summary và top future importance.
  - Đọc warehouse từ `artifacts/warehouse.duckdb`.
- `tests/unit/test_leakage_experiment.py`
  - Cập nhật import sang `pit_feature_store.leakage`, bỏ alias tạm cho root module.
  - Kiểm tra future-only semantics, hai biên window, entity độc lập và UID thiếu.
  - Kiểm tra cohort đủ observation window, schema catalog-driven và time split sau lọc.
  - Kiểm tra ba model, missing value, fraud-rate baseline và nội dung report markdown
    được render từ module.
  - Có regression test static cho research rationale, held-out permutation,
    grouped block shuffle, paired bootstrap, runtime report sections và compile
    toàn bộ code cell notebook.
- `tests/conftest.py`
  - Cung cấp fixture `small_transactions_connection` dùng DuckDB in-memory với ba
    giao dịch nhỏ và tự đóng connection sau test.
  - Fixture được dùng bởi test schema offline hiện có; không thêm hoặc đổi assertion.
- `artifacts/reports/leakage_metrics.csv`
  - Metric do notebook leakage export; bản legacy root đã được xóa.
- `artifacts/reports/leakage_experiment.md`
  - Markdown report do notebook leakage export; bản legacy root đã được xóa.
- `.gitignore`
  - Dùng một rule `artifacts/` thay cho các pattern output riêng lẻ; các artifact
    từng được track đã được bỏ khỏi index nhưng giữ nguyên trên đĩa.
- `uid.py`
  - Đã xóa sau khi logic được hợp nhất vào `src/pit_feature_store/entity_selection.py`;
    notebook là workflow báo cáo chính và không còn consumer cần wrapper root.
- `README.md`
  - Mô tả workflow raw → notebook EDA → warehouse/catalog/offline PIT → notebook
    research → backfill.
  - Phân biệt notebook cho EDA/model research với `src/` cho reusable data logic.
  - Thêm workflow PowerShell từ `pip install -e .` đến EDA, warehouse, catalog,
    offline engine, leakage notebook và test theo đúng src-layout hiện có.
  - Cập nhật mọi đường dẫn warehouse/report sang `artifacts/`.
  - Bỏ bước chạy `uid.py`; notebook EDA là entry point tự tính report từ raw data.
  - Thêm lệnh backfill, output versioned, catalog snapshot và log path.
  - Cập nhật trạng thái/workflow qua Giai đoạn 6; thêm quick start Redis Docker,
    online replay, FastAPI endpoint, test online và cấu trúc source mới.
  - Liên kết tới `STAGE6_ONLINE_ENGINE_API.md`; workflow parity Giai đoạn 7 chưa
    được bổ sung vì cập nhật README thuộc task 10.2, ngoài phạm vi lần này.
- `STAGE6_ONLINE_ENGINE_API.md`
  - Hướng dẫn chi tiết chạy Redis bằng Docker Desktop, replay, API, request mẫu,
    test, quản lý container và troubleshooting.
- `src/pit_feature_store/backfill.py`
  - Đọc `transactions` từ warehouse được attach read-only; không đọc raw CSV.
  - Tính lookback từ `catalog.max_lookback_hours`, chạy PIT engine bằng TEMP objects
    và chỉ xuất cutoff thuộc khoảng ngày inclusive được yêu cầu.
  - Tạo SHA-256 fingerprint rút gọn 16 ký tự, version output, catalog snapshot,
    atomic Parquet replace và JSONL success/failure log.
- `scripts/run_backfill.py`
  - CLI mỏng nhận `--start-date` và `--end-date`.
- `tests/conftest.py`
  - Thêm warehouse fixture nhỏ có full `pit_features` làm reference cho backfill.
- `tests/unit/test_offline_correctness.py`
  - Kiểm tra chế độ backfill tạo `label_spine`, `feature_events`,
    `feature_cumsum`, `pit_features` dưới dạng TEMP objects.
- `tests/integration/test_backfill_idempotent.py`
  - So DataFrame sau hai lần chạy, kiểm tra version/fingerprint, snapshot, atomic
    temp cleanup, log và validate date range.
- `tests/integration/test_backfill_matches_full_pipeline.py`
  - So output backfill với full `pit_features` cùng khoảng và xác nhận bảng chính
    không bị thay đổi.
- `requirements.txt`
  - Thêm `fakeredis==2.37.0`; `httpx` đã có sẵn cho FastAPI `TestClient`.
- `src/pit_feature_store/online_engine.py`
  - Lưu raw event trong Redis ZSET `events:<uid>` với member JSON chứa transaction
    ID/amount và score là epoch.
  - Tính feature theo catalog với interval `[cutoff-window, cutoff)`, gồm cả default
    cho entity chưa có lịch sử và `None` cho `time_since_last` ngoài 720 giờ.
  - Dọn riêng namespace dự án, quản lý virtual clock, chuẩn hóa timestamp giả lập
    theo UTC và replay deterministic theo thứ tự thời gian.
  - Đọc warehouse theo batch trong package để CLI chỉ còn là wrapper mỏng.
- `scripts/run_online_replay.py`
  - CLI nhận warehouse/catalog/Redis URL, gọi replay engine và in kết quả.
- `src/pit_feature_store/serving.py`
  - Export FastAPI `app` và app factory có thể inject Redis client khi test.
  - Endpoint `GET /features/{uid}` hỗ trợ `as_of_epoch`, dùng virtual clock khi bỏ
    qua, trả 503 khi clock chưa sẵn sàng và 422 cho cutoff không hữu hạn.
- `scripts/run_api.py`
  - CLI mỏng chạy Uvicorn với FastAPI app.
- `tests/unit/test_online_engine.py`
  - Kiểm tra ZSET raw, catalog-driven calculation, interval, entity độc lập, event
    cùng timestamp, cleanup, replay compute-before-ingest và virtual clock.
- `tests/integration/test_online_replay.py`
  - Kiểm tra DuckDB → Redis replay theo thứ tự, PIT semantics và không xóa state khi
    warehouse đầu vào không tồn tại.
- `tests/integration/test_serving_api.py`
  - Kiểm tra explicit/implicit cutoff, đủ bốn feature, default entity mới, HTTP 503
    và validation cutoff bằng `TestClient` + `fakeredis`.
- `src/pit_feature_store/parity.py`
  - Lấy mẫu offline deterministic từ `pit_features`, lọc UID thiếu và bắt buộc ít
    nhất 50 mẫu.
  - Tính online từ raw Redis event tại đúng `uid`/`cutoff`, dùng danh sách feature
    từ catalog và không thay đổi offline/online engine.
  - Chuẩn hóa `NULL`/`NaN`/`None`, dùng sai số float nhỏ và trả chi tiết từng
    mismatch.
- `scripts/run_parity.py`
  - CLI nhận warehouse/catalog/Redis URL/sample size, in tổng kết cùng từng
    mismatch và trả exit code khác 0 khi có sai lệch.
- `tests/unit/test_parity_values.py`
  - Kiểm tra chuẩn hóa missing, sai số float, guard tối thiểu 50 mẫu và report CLI.
- `tests/integration/test_parity.py`
  - Nối DuckDB offline pipeline, Redis replay bằng `fakeredis` và parity trên 64
    mẫu; kiểm tra đủ bốn feature, 0 mismatch và chẩn đoán khi cố ý tạo lệch.
- `reports/`
  - Đã xóa toàn bộ thư mục legacy sau khi xác nhận các bản artifact tương ứng.
- `TODO.md`
  - Giữ nguyên lịch sử hoàn thành Giai đoạn 6 và đánh dấu hoàn thành Giai đoạn 7
    (7.1-7.2) sau khi test parity và toàn bộ test đều pass.
  - Giữ task 10.2 chưa hoàn thành cho đến khi README có workflow parity và được
    xác minh từ môi trường sạch.
- `STATUS.md`
  - Ghi nhận phạm vi, lệnh kiểm tra, kết quả và giới hạn của Giai đoạn 7.

## 5. Candidate đã chọn

Candidate cuối cùng là:

`card1 + card2 + addr1`

Candidate này cân bằng độ phủ 87,45%, tỷ lệ entity lặp 60,49% và tỷ lệ
dòng thuộc entity lặp 97,15%; chi tiết hơn `card1 + addr1` nhưng không bị
phân mảnh mạnh như candidate có `D1`.

`src/pit_feature_store/warehouse.py` sử dụng đúng công thức này.

## 6. Lệnh đã chạy

- `.\.venv\Scripts\python.exe --version`
- `.\.venv\Scripts\python.exe -c "import duckdb, pandas, pyarrow, sklearn, lightgbm; print('imports_ok')"`
- Kiểm tra sự tồn tại của hai file raw bằng Python.
- Đếm dòng và kiểm tra tám cột bắt buộc bằng DuckDB.
- `.\.venv\Scripts\python.exe evaluate_entity_candidates.py`
- `.\.venv\Scripts\python.exe init_warehouse.py` (chạy hai lần)
- Truy vấn schema, số dòng, số Transaction ID duy nhất và fingerprint
  logic của bảng `transactions`.
- `.\.venv\Scripts\python.exe -m pytest tests\test_stage1.py -v`
- `.\.venv\Scripts\python.exe catalog.py`
- `.\.venv\Scripts\python.exe -m pytest tests\test_catalog.py -v`
- `.\.venv\Scripts\python.exe -m pytest tests -v`
- `.\.venv\Scripts\python.exe -m pytest tests\test_offline_correctness.py tests\test_time_boundaries.py -v`
- `.\.venv\Scripts\python.exe offline_engine.py`
- Truy vấn schema, loại object, số dòng và mẫu dữ liệu của `label_spine`,
  `feature_events`, `feature_cumsum`, `pit_features`.
- `.\.venv\Scripts\python.exe -m pytest tests\test_leakage_experiment.py -v`
- `.\.venv\Scripts\python.exe leakage_experiment.py`
- `.\.venv\Scripts\python.exe -m pytest tests -v`
- `.\.venv\Scripts\python.exe -m pip install "setuptools>=64"`
- `.\.venv\Scripts\python.exe -m pip install -e .`
- `.\.venv\Scripts\python.exe -c "import pit_feature_store; print(pit_feature_store.__file__)"`
- `.\.venv\Scripts\python.exe -m pytest tests -v` (sau sub-task 4.5.1)
- `.\.venv\Scripts\python.exe -m pytest tests/test_catalog.py tests/test_offline_correctness.py tests/test_time_boundaries.py -v`
- `.\.venv\Scripts\python.exe -m pytest tests -v` (sau sub-task 4.5.2)
- `.\.venv\Scripts\python.exe scripts/init_warehouse.py`
- Truy vấn `SUM(hash(transaction_id, uid, event_ts, amount, label))` sau khi
  chạy CLI mới.
- `.\.venv\Scripts\python.exe -m pytest tests -v` (trước và sau khi xóa
  `init_warehouse.py` root ở sub-task 4.5.3)
- Thực thi tuần tự toàn bộ code cell của
  `notebooks/01_eda_and_entity_selection.ipynb` bằng CLI `nbformat` trong cùng
  namespace Python (`RUN_ALL_OK code_cells=4`).
- So sánh `artifacts/reports/entity_candidate_results.csv` với
  `reports/entity_candidate_results.csv` bằng `pandas.testing.assert_frame_equal`.
- `.\.venv\Scripts\python.exe -m pytest tests -v` (sau sub-task 4.5.4)
- `.\.venv\Scripts\python.exe -m pytest tests/test_leakage_experiment.py -v`
  (sau khi chuyển import sang `pit_feature_store.leakage`)
- `.\.venv\Scripts\python.exe -m jupyter nbconvert --to notebook --execute notebooks\02_leakage_experiment.ipynb --output-dir artifacts\reports --output 02_leakage_experiment.executed.ipynb --ExecutePreprocessor.timeout=900`
- So sánh `artifacts/reports/leakage_metrics.csv` với số liệu chuẩn trong mục 7
  và với `reports/leakage_metrics.csv` legacy bằng `pandas.testing.assert_frame_equal`.
- `.\.venv\Scripts\python.exe -m pytest tests -v` (sau sub-task 4.5.5)
- `.\.venv\Scripts\python.exe -m pytest tests -v` (baseline trước sub-task 4.5.6)
- `.\.venv\Scripts\python.exe -m pytest tests -v` (sau khi sắp xếp unit/integration)
- `.\.venv\Scripts\python.exe scripts/init_warehouse.py` (sau khi chuyển output)
- Truy vấn số dòng, schema và fingerprint logic tại `artifacts/warehouse.duckdb`.
- So sánh SHA-256 ba report legacy với bản trong `artifacts/reports/` trước khi xóa.
- `.\.venv\Scripts\python.exe -m pytest tests -v` (sau sub-task 4.5.7)
- `git check-ignore -v artifacts artifacts/warehouse.duckdb artifacts/reports/*`
- `git ls-files artifacts`
- `git diff --check`
- `.\.venv\Scripts\python.exe -m py_compile src\pit_feature_store\backfill.py src\pit_feature_store\offline_engine.py scripts\run_backfill.py`
- `.\.venv\Scripts\python.exe -m pytest tests\unit\test_offline_correctness.py tests\unit\test_time_boundaries.py tests\integration\test_backfill_idempotent.py tests\integration\test_backfill_matches_full_pipeline.py -v -p no:cacheprovider`
- `.\.venv\Scripts\python.exe scripts\run_backfill.py --help`
- `.\.venv\Scripts\python.exe scripts\run_backfill.py --start-date 2018-01-01 --end-date 2018-01-01`
- Đọc Parquet vừa tạo và so bằng `pandas.testing.assert_frame_equal` với
  `pit_features` cùng ngày; so bytes catalog snapshot với catalog nguồn.
- `.\.venv\Scripts\python.exe -m pytest tests\unit -v -p no:cacheprovider`
- `.\.venv\Scripts\python.exe -m pytest tests -v -p no:cacheprovider`
- Validate hai notebook bằng `nbformat.validate` sau khi cập nhật path.
- `.\.venv\Scripts\python.exe -c "import duckdb, pandas, pyarrow, sklearn, lightgbm; import pit_feature_store; print(pit_feature_store.__file__)"`
- `.\.venv\Scripts\python.exe -m pit_feature_store.catalog`
- `.\.venv\Scripts\python.exe -m pytest tests -v -p no:cacheprovider`
- Kiểm tra toàn bộ local path được nêu trong README bằng PowerShell `Test-Path`.
- `git diff --check` (sau khi cập nhật README).
- `.\.venv\Scripts\python.exe -m pytest tests\unit\test_entity_selection.py -v -p no:cacheprovider`
- Validate notebook bằng `nbformat.validate`; kiểm tra code cell không chứa
  `pd.read_csv`/`source_report_path` và có import `run_entity_selection`.
- `.\.venv\Scripts\python.exe -m jupyter nbconvert --to notebook --execute notebooks\01_eda_and_entity_selection.ipynb --output-dir artifacts\reports --output 01_eda_and_entity_selection.executed.ipynb --ExecutePreprocessor.timeout=900`
- Đối chiếu report vừa sinh với bốn bộ số liệu candidate đã duyệt.
- `.\.venv\Scripts\python.exe -m pytest tests -v -p no:cacheprovider`
- Dùng `rg` kiểm tra mọi tham chiếu `uid.py`, `from uid`, `import uid` trước khi xóa.
- `.\.venv\Scripts\python.exe -m pytest tests -v -p no:cacheprovider`
  (sau khi xóa `uid.py`).
- Validate schema và compile mọi code cell của hai notebook bằng `nbformat`.
- `.\.venv\Scripts\python.exe -m pytest tests\unit -v -p no:cacheprovider`
- `.\.venv\Scripts\python.exe -m jupyter nbconvert --to notebook --execute notebooks\01_eda_and_entity_selection.ipynb --output-dir artifacts\reports --output 01_eda_and_entity_selection.executed.ipynb --ExecutePreprocessor.timeout=900`
- Kiểm tra notebook 01 không có error và execution count liên tục từ 1 đến 12.
- `.\.venv\Scripts\python.exe scripts\init_warehouse.py`
- `.\.venv\Scripts\python.exe -m pit_feature_store.offline_engine`
- `.\.venv\Scripts\python.exe -m jupyter nbconvert --to notebook --execute notebooks\02_leakage_experiment.ipynb --output-dir artifacts\reports --output 02_leakage_experiment.executed.ipynb --ExecutePreprocessor.timeout=900`
- Kiểm tra notebook 02 không có error, execution count 1 đến 13 và đối chiếu metrics.
- `.\.venv\Scripts\python.exe -m pytest tests -v -p no:cacheprovider`
- `.\.venv\Scripts\python.exe -m jupyter nbconvert --to notebook --execute --inplace notebooks\01_eda_and_entity_selection.ipynb --ExecutePreprocessor.timeout=900`
- `.\.venv\Scripts\python.exe -m jupyter nbconvert --to notebook --execute --inplace notebooks\02_leakage_experiment.ipynb --ExecutePreprocessor.timeout=900`
- Validate hai source notebook sau Run All: execution count liên tục, không output
  error; notebook 02 không chứa `run_experiment` và có Dummy/fit/predict code.
- `.\.venv\Scripts\python.exe -m pytest tests\unit\test_leakage_experiment.py -v -p no:cacheprovider`
  sau khi xóa model/report API khỏi `leakage.py`.
- `.\.venv\Scripts\python.exe -m jupyter nbconvert --to notebook --execute --inplace notebooks\02_leakage_experiment.ipynb --ExecutePreprocessor.timeout=900`
  sau khi đưa `train_fraction=0.8` thành cấu hình nhìn thấy trong notebook.
- Validate notebook 02 bằng `nbformat`: 13 code cell, execution count 1-13, không
  error, không có `run_experiment`, có `.fit()` và `predict_proba()`.
- `.\.venv\Scripts\python.exe -m pytest tests\unit -v -p no:cacheprovider`
- `.\.venv\Scripts\python.exe -m pytest tests -v -p no:cacheprovider`
- `git diff --check`
- `.\.venv\Scripts\python.exe -m pip install fakeredis==2.37.0`
- `.\.venv\Scripts\python.exe -B -m py_compile src\pit_feature_store\online_engine.py src\pit_feature_store\serving.py scripts\run_online_replay.py scripts\run_api.py tests\unit\test_online_engine.py tests\integration\test_online_replay.py tests\integration\test_serving_api.py`
- `.\.venv\Scripts\python.exe -B scripts\run_online_replay.py --help`
- `.\.venv\Scripts\python.exe -B -m pytest tests\integration\test_serving_api.py -v -p no:cacheprovider`
- `.\.venv\Scripts\python.exe -B -m pytest tests\unit\test_online_engine.py tests\integration\test_online_replay.py tests\integration\test_serving_api.py -v -p no:cacheprovider`
- `.\.venv\Scripts\python.exe -B -m pytest tests -v -p no:cacheprovider`
- Kiểm tra toàn bộ path local được thêm vào README bằng PowerShell `Test-Path`.
- Dùng `rg` xác nhận README không còn tuyên bố online engine chưa triển khai.
- `git diff --check -- README.md TODO.md STATUS.md STAGE6_ONLINE_ENGINE_API.md`
- `.\.venv\Scripts\python.exe -B -m pytest tests\unit\test_leakage_experiment.py tests\unit\test_offline_correctness.py tests\unit\test_time_boundaries.py tests\unit\test_catalog.py -v -p no:cacheprovider`
- `.\.venv\Scripts\python.exe -m jupyter nbconvert --to notebook --execute --inplace notebooks\02_leakage_experiment.ipynb --ExecutePreprocessor.timeout=1200`
- Validate notebook 02 bằng `nbformat`: 42 cell, 19 code cell, execution count
  liên tục 1-19, ID duy nhất, không error output và mọi code cell compile được.
- `.\.venv\Scripts\python.exe -B -m pytest tests\integration\test_backfill_idempotent.py::test_backfill_is_logically_idempotent_and_writes_versioned_outputs -v -p no:cacheprovider`
- `.\.venv\Scripts\python.exe -B -m pytest tests -v -p no:cacheprovider`

- Kiểm tra compile in-memory cho `src/pit_feature_store/parity.py`,
  `scripts/run_parity.py`, `tests/unit/test_parity_values.py` và
  `tests/integration/test_parity.py` bằng built-in `compile()`.
- Chạy `scripts/run_parity.py --help` bằng Python trong `.venv`.
- Chạy riêng `tests/unit/test_parity_values.py` và
  `tests/integration/test_parity.py` bằng pytest verbose, tắt cache provider.
- Chạy toàn bộ `tests/` bằng pytest verbose, tắt cache provider.
- `git diff --check -- src/pit_feature_store/parity.py scripts/run_parity.py tests/unit/test_parity_values.py tests/integration/test_parity.py TODO.md STATUS.md`

## 7. Kết quả

- Python: 3.13.7.
- Import `duckdb`, `pandas`, `pyarrow`, `sklearn`, `lightgbm`: thành công.
- Hai file raw tồn tại.
- `train_transaction.csv`: 590.540 dòng và đủ tám cột bắt buộc.
- Báo cáo pseudo-entity: 4 candidate, đủ các thống kê bắt buộc.
- Script candidate chạy thành công sau khi sửa lỗi encoding.
- Warehouse có 590.540 dòng và 590.540 Transaction ID duy nhất.
- Schema gồm `transaction_id`, `uid`, `event_ts`, `amount`, `label`.
- UID khớp `card1 + card2 + addr1` trên toàn bộ dữ liệu.
- Hai lần chạy warehouse có cùng fingerprint logic:
  `5448808371316238155834275`.
- Test Giai đoạn 1: 3 passed trong 5,62 giây ở lần chạy cuối.
- Catalog load và validate thành công với đúng bốn feature:
  - Tất cả feature có description, entity `uid`, event time `event_ts`
    và version `1.0.0`.
  - `sum_amt_24h`: `sum`, `amount`, 24 giờ, mặc định 0.
  - `count_txn_24h`: `count`, `transaction_id`, 24 giờ, mặc định 0.
  - `sum_amt_7d`: `sum`, `amount`, 168 giờ, mặc định 0.
  - `time_since_last_txn_sec`: `time_since_last`, `event_ts`,
    720 giờ, mặc định `None`.
- Catalog version: `1.0.0`.
- Max lookback: 720 giờ.
- Test riêng catalog: 20 passed trong 1,39 giây.
- Toàn bộ test hiện có: 23 passed trong 6,20 giây.
- Offline pipeline tạo:
  - `label_spine`: view, 590.540 dòng.
  - `feature_events`: view, 516.425 dòng có UID hợp lệ.
  - `feature_cumsum`: view, cumulative sum/count partition theo UID.
  - `pit_features`: bảng, 590.540 dòng và đủ bốn feature.
- Test riêng Giai đoạn 3: 11 passed trong 8,41 giây ở lần chạy chi tiết;
  11 passed trong 1,94 giây sau khi tối ưu bằng `ASOF JOIN`.
- Toàn bộ test sau Giai đoạn 3: 34 passed trong 6,96 giây.
- CLI offline engine chạy thành công trên full warehouse và tạo 590.540 dòng.
- Test riêng Giai đoạn 4 sau hiệu chỉnh: 6 passed trong 4,03 giây ở lần chạy cuối.
- Leakage experiment hiệu chỉnh dùng cohort từ `2018-01-01 00:00:00` đến
  `2018-05-02 23:58:51`, bảo đảm đủ 720 giờ ở hai phía:
  - 370.770 dòng hợp lệ; loại 219.770 trên tổng 590.540 dòng.
  - Split timestamp `2018-04-05 23:19:56`: train 296.615 dòng, test 74.155 dòng.
  - Test có 2.527 fraud, tỷ lệ `0.034077`, là baseline ngẫu nhiên của PR-AUC.
  - PIT: ROC-AUC `0.679783`, PR-AUC `0.067894`, lift `1.992x`.
  - Future-only: ROC-AUC `0.674214`, PR-AUC `0.064931`, lift `1.905x`.
  - PIT + future: ROC-AUC `0.705485`, PR-AUC `0.074536`, lift `2.187x`.
  - Phép thử kiểm soát PIT + future cao hơn PIT `0.025702` ROC-AUC và
    `0.006641` PR-AUC; future-only vẫn là phép so sánh phụ theo đặc tả.
  - Kết luận dựa trên kết quả thực tế, không giả định future feature phải làm metric tăng.
- Toàn bộ test sau khi hiệu chỉnh Giai đoạn 4: 40 passed trong 10,90 giây.
- Package editable `pit-feature-store==0.1.0` được build và cài thành công.
- `pit_feature_store` import thành công từ `src/pit_feature_store/__init__.py`.
- Toàn bộ test sau sub-task 4.5.1: 40 passed trong 12,00 giây.
- Ba test mục tiêu của 4.5.2: 31 passed trong 3,89 giây trước khi xóa bản root.
- Toàn bộ test sau khi xóa bản root: 40 passed trong 9,41 giây.
- `catalog.py`, `offline_engine.py` và `feature_catalog.yaml` bản root đã được
  xóa sau khi vị trí mới hoạt động đúng.
- CLI mới tạo 590.540 dòng với schema `transaction_id`, `uid`, `event_ts`,
  `amount`, `label` và fingerprint logic
  `5448808371316238155834275`.
- Toàn bộ test sub-task 4.5.3: 40 passed trong 10,65 giây trước khi xóa file
  root; 40 passed trong 9,65 giây sau khi xóa.
- `init_warehouse.py` bản root đã được xóa sau khi fingerprint và test khớp.
- Notebook EDA chạy đủ 4 code cell, tạo chart và export report không lỗi.
- Report mới khớp chính xác report legacy trên toàn bộ 4 dòng/cột; candidate
  chọn vẫn là `card1 + card2 + addr1` với coverage 87,45%, repeat entity
  60,49% và repeat row 97,15%.
- Toàn bộ test sau sub-task 4.5.4: 40 passed trong 11,39 giây.
- `evaluate_entity_candidates.py` bản root đã được xóa sau khi notebook/output
  được xác minh.
- Test riêng leakage sau sub-task 4.5.5: 6 passed trong 2,46 giây.
- Notebook leakage chạy bằng `nbconvert --execute` thành công và ghi bản executed
  tại `artifacts/reports/02_leakage_experiment.executed.ipynb`.
- `artifacts/reports/leakage_metrics.csv` khớp `reports/leakage_metrics.csv`
  legacy; metric khớp số liệu đã duyệt trong sai số làm tròn dưới `1e-6`:
  - PIT: ROC-AUC `0.6797832391`, PR-AUC `0.0678943276`.
  - Future-only: ROC-AUC `0.6742140266`, PR-AUC `0.0649309156`.
  - PIT + future: ROC-AUC `0.7054850751`, PR-AUC `0.0745357016`.
  - Cohort: `2018-01-01 00:00:00` đến `2018-05-02 23:58:51`; split
    `2018-04-05 23:19:56`.
- Toàn bộ test sau sub-task 4.5.5: 40 passed trong 8,79 giây.
- `leakage_experiment.py` bản root đã được xóa sau khi module mới, notebook,
  metric và test được xác minh.
- Baseline trước sub-task 4.5.6: 40 passed trong 12,22 giây.
- Sau khi sắp xếp lại test: 40 passed trong 8,89 giây; số lượng test và assertion
  nghiệp vụ được giữ nguyên.
- Phân loại đã xác minh từ code:
  - Unit: `test_catalog.py`, `test_offline_correctness.py`,
    `test_time_boundaries.py`, `test_leakage_experiment.py`; các test này dùng file
    tạm, DuckDB in-memory hoặc DataFrame nhỏ tự tạo và không mở warehouse thật.
  - Integration: `test_stage1.py`; file này đọc CSV Kaggle/report thật, mở
    `warehouse.duckdb` và đối chiếu warehouse với raw CSV.
- CLI sau sub-task 4.5.7 tạo `artifacts/warehouse.duckdb` với 590.540 dòng,
  schema `transaction_id`, `uid`, `event_ts`, `amount`, `label` và fingerprint
  logic `5448808371316238155834275`.
- `warehouse.duckdb` và `reports/` ở root đã được xóa sau khi output mới được xác minh.
- `entity_candidate_results.csv` và `leakage_metrics.csv` legacy khớp SHA-256 với
  bản artifact. `leakage_experiment.md` artifact là report mới do notebook sinh;
  bản markdown legacy đã được dọn khỏi root.
- Toàn bộ test sau sub-task 4.5.7: 40 passed trong 8,91 giây.
- `artifacts/` bị ignore bởi đúng rule `.gitignore: artifacts/`; không còn file
  artifact nào trong `git ls-files` và không xuất hiện dưới dạng untracked.
- Toàn bộ 7 sub-task Giai đoạn 4.5 đã hoàn thành. Các file chính thức trong bảng
  ánh xạ mục 21, cấu trúc tests và output layout đã chuyển sang src-layout.
- Import dependency chính và package editable thành công từ
  `src/pit_feature_store/__init__.py` sau khi cập nhật README.
- Catalog CLI trả đúng version `1.0.0`, max lookback 720 giờ và đủ bốn feature.
- Toàn bộ test sau khi cập nhật README: 40 passed trong 9,75 giây.
- Tất cả local path được tài liệu hóa trong README tồn tại; `git diff --check`
  không báo lỗi whitespace.
- Regression test entity-selection: 2 passed trong 1,13 giây.
- Notebook EDA chạy thành công trên 590.540 raw transaction, tự tạo report và bản
  executed notebook; không đọc report cũ làm input.
- Report mới khớp toàn bộ thống kê đã duyệt của bốn candidate và tiếp tục chọn
  `card1 + card2 + addr1`.
- Toàn bộ test sau khi sửa notebook EDA: 42 passed trong 8,83 giây.
- Không còn consumer runtime/test/tài liệu nào phụ thuộc `uid.py`; file đã được xóa.
- Toàn bộ test sau khi xóa wrapper `uid.py`: 42 passed trong 9,19 giây.
- Unit tests sau refactor mentor: 39 passed trong 4,49 giây.
- Notebook 01 Run All từ kernel sạch thành công trong 79,6 giây; 12 code cell có
  execution count 1-12, không error và report entity có 4 candidate.
- Warehouse được build lại với 590.540 dòng; offline engine tạo lại 590.540 PIT rows.
- Notebook 02 Run All từ kernel sạch thành công trong 13,7 giây; 13 code cell có
  execution count 1-13 và không error.
- Dummy baseline: ROC-AUC `0.500000`, PR-AUC `0.034077` (gần test fraud prevalence).
- Ba LightGBM metric không đổi so với kết quả đã duyệt:
  - PIT: ROC-AUC `0.6797832391`, PR-AUC `0.0678943276`.
  - Future-only: ROC-AUC `0.6742140266`, PR-AUC `0.0649309156`.
  - PIT + future: ROC-AUC `0.7054850751`, PR-AUC `0.0745357016`.
- Toàn bộ regression tests sau refactor: 42 passed trong 9,00 giây.
- Hai source notebook đã được lưu sau Restart/Run All (không chỉ bản artifact):
  notebook 01 có execution count 1-12, notebook 02 có execution count 1-13; toàn
  bộ output/chart/table có sẵn khi reviewer mở file.
- Sau khi làm sạch boundary research/engineering, test riêng leakage: 5 passed trong
  4,61 giây; unit tests: 38 passed trong 2,09 giây; toàn bộ tests: 41 passed trong
  7,14 giây. Hai test cũ cho model/report helper đã được bỏ và thay bằng regression
  test kiểm tra ba feature frame dùng chung label spine.
- Notebook 02 Run All lại thành công trong 21,6 giây; Dummy/PIT/future/PIT+future
  metrics không đổi. `train_fraction=0.8` hiện rõ trong notebook và được truyền vào
  data-preparation helper.
- Test liên quan Giai đoạn 5: 15 passed trong 16,22 giây.
- Unit tests sau Giai đoạn 5: 39 passed trong 2,19 giây.
- Toàn bộ tests sau Giai đoạn 5: 45 passed trong 7,47 giây.
- CLI backfill trên warehouse thật cho ngày `2018-01-01` tạo 2.982 dòng, dùng
  lookback 720 giờ và version `1.0.0-a56eaf7727288928`.
- Parquet CLI khớp full `pit_features` cùng ngày; catalog snapshot khớp file nguồn;
  backfill log ghi success. Integration test xác nhận chạy hai lần cho DataFrame
  bằng nhau và không thay đổi bảng `pit_features` chính.
- `fakeredis==2.37.0` cài thành công cùng dependency `sortedcontainers==2.4.0`;
  Redis thật không cần cho test Giai đoạn 6.
- Online engine trả đúng bốn feature catalog-driven từ raw Redis events, bao gồm
  biên dưới và loại event tại cutoff; entity mới và entity độc lập cho kết quả đúng.
- Replay DuckDB sắp theo `event_ts, transaction_id`, compute trước ingest, bỏ ingest
  UID thiếu nhưng vẫn tiến virtual clock, chỉ xóa key thuộc dự án và chạy lại cho
  cùng Redis state.
- API dùng cutoff tường minh hoặc `sys:virtual_now_epoch`, trả HTTP 503 khi thiếu
  clock và HTTP 422 cho `NaN`/`Infinity`.
- Test liên quan Giai đoạn 6: 19 passed trong 1,75 giây.
- Toàn bộ tests sau Giai đoạn 6: 64 passed trong 10,69 giây.
- README mô tả đúng workflow Giai đoạn 6, có lệnh Redis Docker/replay/API, endpoint,
  test mục tiêu, source tree mới và liên kết hướng dẫn chi tiết.
- Tất cả path local được thêm vào README tồn tại; kiểm tra Markdown/diff không báo
  lỗi.
- Controlled leakage analysis Run All thành công trong 78,9 giây trên 370.770
  eligible rows và 74.155 held-out rows; 19 code cell có execution count 1-19,
  không error và metric bốn model không đổi.
- Timeline dùng transaction test thật `3417954` tại cutoff
  `2018-04-05 23:19:56`: 3 event trước cutoff, 1 event tại cutoff bị loại và 4
  event sau cutoff trong cửa sổ 24 giờ.
- Held-out permutation importance theo average precision cho cả bốn future feature
  đều dương; cao nhất là `time_to_next_txn_sec` với
  `0.033729 ± 0.000523`.
- 50 grouped future-block shuffles (không retrain) cho mean:
  - ROC-AUC `0.581831 ± 0.004504`, thấp hơn original PIT + Future `0.705485`
    ở cả 50/50 lần; original-minus-shuffled mean `+0.123655`.
  - PR-AUC `0.043190 ± 0.000695`, thấp hơn original `0.074536` ở cả 50/50
    lần; original-minus-shuffled mean `+0.031346`.
- 500/500 paired bootstrap samples hợp lệ:
  - ROC-AUC delta point `+0.025702`, mean `+0.025659`, percentile 95% CI
    `[+0.018583, +0.032644]`, proportion delta dương `1.000`.
  - PR-AUC delta point `+0.006641`, mean `+0.006828`, percentile 95% CI
    `[+0.004260, +0.009443]`, proportion delta dương `1.000`.
- Test mục tiêu cho leakage/offline/boundary/catalog: 38 passed trong 3,95 giây.
- Toàn bộ test sau task 4.4: 65 passed trong 9,74 giây; còn một
  `StarletteDeprecationWarning` đã biết.

- Parity integration chạy trên 64 mẫu deterministic và so đủ bốn feature, tương
  đương 256 phép so; kết quả mismatch bằng 0.
- Test mismatch có chủ đích trả đúng context gồm `label_id`, `uid`, `cutoff_ts`,
  tên feature, giá trị offline/online và lý do; report CLI trả exit code 1.
- Test riêng Giai đoạn 7: 6 passed trong 1,65 giây.
- Toàn bộ test sau Giai đoạn 7: 71 passed trong 10,25 giây; còn một
  `StarletteDeprecationWarning` đã biết.

## 8. Vấn đề còn lại

- Chưa chạy replay toàn bộ 590.540 giao dịch hoặc API với Redis server thật; test
  bắt buộc dùng `fakeredis` đã pass nhưng hiệu năng Redis thật chưa được đo. Vì
  vậy CLI parity chưa được xác minh end-to-end với Redis thật/full warehouse.
- FastAPI `TestClient` phát một `StarletteDeprecationWarning` về `httpx`/`httpx2`;
  không ảnh hưởng 71 test nhưng cần xử lý khi task dependency/documentation cho phép.
- README đã mô tả Giai đoạn 6; task 10.2 vẫn chưa hoàn thành vì workflow parity
  chưa được bổ sung và toàn bộ hướng dẫn chưa được xác minh từ môi trường sạch.
- Chưa tái tạo một virtual environment hoàn toàn mới trong lần cập nhật tài liệu;
  các entry point/import được xác minh trên `.venv` hiện có và toàn bộ test đã chạy.
- Cảnh báo ZMQ/TCP của Jupyter xuất hiện trên Windows khi chạy `nbconvert`, nhưng
  cả hai kernel hoàn tất không error và output notebook được ghi thành công.
- Paired bootstrap hiện resample theo row và chỉ định lượng uncertainty conditional
  trên fixed temporal split/fitted models; chưa bao phủ retraining, split uncertainty
  hoặc dependence giữa nhiều transaction cùng `uid` (cluster bootstrap là phân tích
  rộng hơn, ngoài task này).
- Lượt chạy full test đầu tiên của task 4.4 gặp `WinError 5` tạm thời khi backfill
  replace catalog snapshot trong thư mục pytest temp; test đó pass ngay khi chạy
  riêng và full suite kế tiếp pass 65/65, nên không sửa backfill ngoài phạm vi.
- Catalog, offline engine, warehouse, EDA, leakage experiment, tests và output
  chính thức đã ở cấu trúc mới theo `PROJECT_SPEC.md` mục 21.
- `tests/integration/test_stage1.py` vẫn phụ thuộc CSV Kaggle, report và
  `warehouse.duckdb` thật. Trong file này, hai test kiểm tra dataset/report đang đi
  cùng integration suite vì chưa được tách khỏi test warehouse; về phạm vi từng
  component có thể refactor sang fixture/artifact nhỏ sau. Test đối chiếu warehouse
  với raw CSV là integration đúng nghĩa.
- Không còn file Python nghiên cứu/entity-selection dư thừa ở root.

Giai đoạn 7 đã hoàn thành trong phạm vi module parity, CLI và test tự động; không
thực hiện nội dung monitoring của Giai đoạn 8.

## 9. Task tiếp theo

Task tiếp theo theo `TODO.md` là **8.1 — Freshness monitoring**.
Chưa bắt đầu Giai đoạn 8; cần chờ người dùng xác nhận riêng.

Không tự thực hiện cho đến khi có yêu cầu.
