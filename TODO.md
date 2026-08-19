# TODO — Point-in-Time Correct Feature Store

## Quy ước trạng thái

- `[ ]`: Chưa làm
- `[-]`: Đang làm
- `[x]`: Hoàn thành
- `[~]`: Bỏ qua có chủ đích

Không đánh dấu `[x]` nếu chưa chạy điều kiện kiểm tra.

---

## Giai đoạn 1 — Setup và dữ liệu

### [x] 1.1 Xác minh môi trường

File liên quan:

- `requirements.txt`
- `.venv/`

Hoàn thành khi:

`python -c "import duckdb, pandas, pyarrow, sklearn, lightgbm"` không lỗi.

### [x] 1.2 Xác minh dataset IEEE-CIS

File liên quan:

- `data/raw/ieee/train_transaction.csv`
- `data/raw/ieee/train_identity.csv`

Hoàn thành khi:

- `train_transaction.csv` tồn tại.
- Có 590.540 dòng dữ liệu, không tính header.
- Có các cột bắt buộc: `TransactionID`, `TransactionDT`, `TransactionAmt`, `isFraud`, `card1`, `card2`, `addr1`, `D1`.

### [x] 1.3 Đánh giá pseudo-entity

File: `evaluate_entity_candidates.py` (root — bản flat cũ, sẽ được thay bằng notebook ở Giai đoạn 4.5)

Output: `reports/entity_candidate_results.csv`

Hoàn thành khi:

- Đánh giá ít nhất ba candidate.
- Output có số entity, tỷ lệ entity lặp lại, max transaction/entity.
- Candidate cuối cùng được chọn và có giải thích.

**Kết quả:** candidate đã chọn là `card1 + card2 + addr1` (xem `STATUS.md` mục 5 để biết lý do chi tiết).

### [x] 1.4 Khởi tạo warehouse

File: `init_warehouse.py` (root — bản flat cũ, sẽ tách thành `warehouse.py` + `scripts/init_warehouse.py` ở Giai đoạn 4.5)

Output: `warehouse.duckdb`

Hoàn thành khi:

- Bảng `transactions` tồn tại, có 590.540 dòng.
- Có `uid`, `event_ts`, amount, label.
- UID dùng đúng candidate đã chọn.
- Script chạy lại không tạo dữ liệu trùng.

---

## Giai đoạn 2 — Feature catalog

### [x] 2.1 Tạo feature catalog

Tạo: `feature_catalog.yaml` (root — sẽ chuyển sang `config/feature_catalog.yaml` ở Giai đoạn 4.5)

Hoàn thành khi có đủ `sum_amt_24h`, `count_txn_24h`, `sum_amt_7d`, `time_since_last_txn_sec`, có version catalog, mỗi feature có description/entity/aggregation/source column/window/event time/default value.

### [x] 2.2 Tạo catalog loader

Tạo: `catalog.py` (root — sẽ chuyển sang `src/pit_feature_store/catalog.py` ở Giai đoạn 4.5)

Hoàn thành khi: load YAML, validate Pydantic, chỉ chấp nhận aggregation hỗ trợ, window hợp lệ, tên feature SQL-safe, có `max_lookback_hours`, YAML rỗng báo lỗi rõ ràng, `python catalog.py` in đủ bốn feature.

### [x] 2.3 Test feature catalog

Tạo: `tests/test_catalog.py`

Hoàn thành khi: `python -m pytest tests/test_catalog.py -v` pass.

---

## Giai đoạn 3 — Offline engine

### [x] 3.1 Tạo label spine và feature events

Tạo: `offline_engine.py` (root — sẽ chuyển sang `src/pit_feature_store/offline_engine.py` ở Giai đoạn 4.5)

Hoàn thành khi: `label_spine` chỉ chứa label metadata, `feature_events` chỉ chứa event history, hai view query được.

### [x] 3.2 Tạo cumulative feature view

Hoàn thành khi: có `feature_cumsum`, cumulative sum/count, partition đúng theo `uid`.

### [x] 3.3 Tạo PIT join

Hoàn thành khi: có bảng `pit_features`, đủ bốn feature, event tại cutoff bị loại trừ, window dùng `[cutoff-window, cutoff)`.

### [x] 3.4 Test offline correctness

Tạo: `tests/test_offline_correctness.py`

Hoàn thành khi: DuckDB khớp tính tay bằng Pandas, test pass.

### [x] 3.5 Test biên thời gian

Tạo: `tests/test_time_boundaries.py`

Phải kiểm tra: biên dưới được bao gồm, event tại cutoff bị loại, gap >24h/>7 ngày/>720 giờ.

Hoàn thành khi test pass.

---

## Giai đoạn 4 — Leakage experiment

### [x] 4.1 Tạo leaky features

Tạo: `leakage_experiment.py` (root — bản flat cũ, sẽ tách thành `leakage.py` + notebook ở Giai đoạn 4.5)

Hoàn thành khi: leaky feature chỉ dùng tương lai, cùng tên feature với PIT, cùng độ dài window với PIT.

### [x] 4.2 Train baseline và ba model research

Hoàn thành khi: train Dummy baseline, PIT, future-only và PIT + future; các model
dùng cùng temporal split theo `cutoff_ts` và code train/evaluate nhìn thấy trong
notebook.

### [x] 4.3 Xuất metric

Hoàn thành khi có ROC-AUC/PR-AUC cho cả PIT và leaky. Không yêu cầu leaky metric bắt buộc phải cao hơn.

**Kết quả:** xem `STATUS.md` mục 7 — 3 model đã train (PIT, future-only, pit_plus_future), số liệu ROC-AUC/PR-AUC đầy đủ, kết luận dựa trên số liệu thực tế.

### [x] 4.4 Controlled leakage analysis dựa trên research

File liên quan: `notebooks/02_leakage_experiment.ipynb`,
`tests/unit/test_leakage_experiment.py`.

Hoàn thành khi:

- Phân biệt rõ leakage existence (availability violation) với measured impact.
- Có timeline từ transaction thật minh họa event trước, tại và sau cutoff.
- Có permutation importance của PIT + Future model trên held-out test set với
  scoring average precision.
- Có grouped future-block shuffle 30-100 lần, giữ model/PIT/label/test rows và
  không retrain.
- Có paired bootstrap ít nhất 500 lần, dùng cùng row indices cho PIT và
  PIT + Future, báo point estimate, 95% interval và proportion delta dương.
- Evidence summary, conclusion và Markdown report lấy kết quả từ runtime variables,
  không hard-code hoặc ép kết luận ngược dữ liệu.
- Section/chart/report title giữ tiếng Anh; phần mô tả, interpretation và
  conclusion viết bằng tiếng Việt.
- Notebook Run All từ kernel sạch, JSON/schema/code cell hợp lệ và test liên quan pass.

**Kết quả:** notebook chạy đủ 19 code cell; 50 future-block permutations và 500
paired bootstrap samples hoàn tất deterministic. Xem `STATUS.md` mục 7 cho kết quả
thực nghiệm và uncertainty interval. Notebook/report dùng title tiếng Anh và phần
diễn giải tiếng Việt.

---

## Giai đoạn 4.5 — Migrate sang cấu trúc src-layout

> Bối cảnh: Giai đoạn 1-4 hoàn thành dưới cấu trúc flat (mọi `.py` ở root). Cấu trúc mới (xem `PROJECT_SPEC.md` mục 21) tách `src/`/`scripts/`/`notebooks/`/`tests/unit+integration`/`artifacts/`. Đây là task **di dời cơ học** — không được đổi logic tính toán hay kết quả đã có, chỉ đổi vị trí file, import path, và cách trình bày (EDA/leakage sang notebook).

**Trạng thái: [x] Hoàn thành toàn bộ Giai đoạn 4.5 (4.5.1-4.5.7).**

### [x] 4.5.1 Tạo khung thư mục mới

File liên quan: `pyproject.toml`, `src/pit_feature_store/__init__.py`, `config/`, `scripts/`, `notebooks/`, `tests/unit/`, `tests/integration/`

Hoàn thành khi:

- Cấu trúc thư mục khớp `PROJECT_SPEC.md` mục 21.
- `pip install -e .` chạy không lỗi.
- `python -c "import pit_feature_store"` không lỗi.

### [x] 4.5.2 Di dời catalog.py và offline_engine.py

Hoàn thành khi:

- `catalog.py` → `src/pit_feature_store/catalog.py`.
- `offline_engine.py` → `src/pit_feature_store/offline_engine.py`.
- `feature_catalog.yaml` → `config/feature_catalog.yaml`, cập nhật default path trong `catalog.py`.
- `test_catalog.py`, `test_offline_correctness.py`, `test_time_boundaries.py` chạy pass sau khi sửa import — không sửa assertion, không đổi logic.

### [x] 4.5.3 Tách warehouse.py khỏi init_warehouse.py

Hoàn thành khi:

- Logic build bảng `transactions` chuyển vào `src/pit_feature_store/warehouse.py` (dạng hàm, không phải script chạy thẳng).
- `scripts/init_warehouse.py` chỉ còn là CLI mỏng gọi lại hàm trên.
- Chạy `python scripts/init_warehouse.py` cho kết quả giống hệt bản cũ (so fingerprint logic đã ghi ở `STATUS.md` mục 7: `5448808371316238155834275`).

### [x] 4.5.4 Chuyển EDA sang notebook

Hoàn thành khi:

- Logic tính/export candidate metrics nằm tại `src/pit_feature_store/entity_selection.py`;
  module không tự quyết định candidate bằng threshold research tùy ý.
- `notebooks/01_eda_and_entity_selection.ipynb` import logic dùng chung, tự quét
  `data/raw/ieee/train_transaction.csv`; không đọc
  `artifacts/reports/entity_candidate_results.csv` làm đầu vào.
- Notebook có dataset overview, statistics, missing/data-quality checks, fraud-label,
  amount/temporal visualization và trình bày quyết định candidate từ số liệu vừa tính.
- Notebook `Run All` không lỗi, export ra đúng `artifacts/reports/entity_candidate_results.csv` với candidate giống `STATUS.md` mục 5 (`card1 + card2 + addr1`).
- `evaluate_entity_candidates.py` (bản `.py` cũ) xoá khỏi root sau khi notebook thay thế xong.
- `uid.py` được xoá sau khi toàn bộ logic đã hợp nhất vào
  `src/pit_feature_store/entity_selection.py`; không giữ wrapper root dư thừa.
- Có regression test cho logic tính report và lỗi thiếu cột raw bắt buộc.

### [x] 4.5.5 Tách leakage.py khỏi leakage_experiment.py

Hoàn thành khi:

- Logic dùng chung để build PIT/future datasets, observation bounds, temporal split
  và load frame nằm trong `src/pit_feature_store/leakage.py`.
- `notebooks/02_leakage_experiment.ipynb` trực tiếp hiển thị feature exploration,
  Dummy baseline, `LGBMClassifier` initialization/fit/predict, metrics, ROC/PR curve,
  PIT feature importance và kết luận.
- `src/pit_feature_store/leakage.py` không chứa model training, metric evaluation,
  experiment orchestration hoặc research report; các test module chỉ kiểm tra
  dataset preparation, boundary và temporal split semantics.
- Notebook không gọi `run_experiment()` để che research flow.
- Notebook tái tạo đúng 3 model đã có (PIT, future-only, pit_plus_future) và ra số liệu khớp `STATUS.md` mục 7 — nếu số lệch, phải ghi rõ lý do (ví dụ khác random seed).
- Export `artifacts/reports/leakage_metrics.csv` và `artifacts/reports/leakage_experiment.md`.
- `leakage_experiment.py` (bản `.py` cũ) xoá khỏi root sau khi notebook thay thế xong.
- `tests/test_leakage_experiment.py` sửa lại để test `src/pit_feature_store/leakage.py` (test hàm logic, không test notebook).

### [x] 4.5.6 Sắp xếp lại tests/ thành unit/ và integration/

Hoàn thành khi:

- Từng test hiện có được xác nhận: phụ thuộc `warehouse.duckdb` build từ full Kaggle CSV, hay dùng fixture nhỏ tự tạo?
- Test không phụ thuộc data thật, chỉ test 1 component → `tests/unit/`.
- Test cần nhiều component nối nhau (CLI thật, warehouse thật) → `tests/integration/`.
- `tests/conftest.py` có fixture DuckDB in-memory nhỏ dùng chung cho `tests/unit/` (sẵn sàng cho Giai đoạn 6-7, chưa bắt buộc dùng ngay).
- `python -m pytest tests -v` toàn bộ vẫn pass sau khi sắp xếp lại (không đổi assertion).

### [x] 4.5.7 Chuyển output sang artifacts/

Hoàn thành khi:

- `warehouse.duckdb` → `artifacts/warehouse.duckdb`.
- `reports/` → `artifacts/reports/`.
- `.gitignore` cập nhật để chặn toàn bộ `artifacts/` thay vì từng file riêng lẻ.
- Mọi đường dẫn hardcode trong code trỏ đúng vị trí mới.

---

## Giai đoạn 5 — Backfill

**Trạng thái: [x] Hoàn thành toàn bộ Giai đoạn 5 (5.1-5.4).**

### [x] 5.1 Tạo backfill

Tạo: `src/pit_feature_store/backfill.py` (logic), `scripts/run_backfill.py` (CLI mỏng, nhận `--start-date`/`--end-date`)

Hoàn thành khi:

- Nhận start date, end date.
- Tính từ raw transactions (đọc qua `warehouse.py`, không tự query lại raw CSV).
- Có lookback (tự tính từ `catalog.py`, dùng `max_lookback_hours` đã có từ Giai đoạn 2).
- Sử dụng TEMP objects.

### [x] 5.2 Thêm version và output an toàn

Hoàn thành khi:

- Có catalog fingerprint, catalog snapshot.
- Output directory theo version, dưới `artifacts/offline_store/backfill/version=<version>/<start>_<end>/`.
- Ghi file tạm rồi replace.
- Backfill log tại `artifacts/logs/backfill_log.jsonl`.

### [x] 5.3 Test idempotency

Tạo: `tests/integration/test_backfill_idempotent.py`

Hoàn thành khi: chạy hai lần cùng tham số, hai DataFrame bằng nhau, test pass.

### [x] 5.4 Test backfill khớp full pipeline

Tạo: `tests/integration/test_backfill_matches_full_pipeline.py`

Hoàn thành khi: backfill output khớp `pit_features` trên cùng khoảng thời gian, test pass.

---

## Giai đoạn 6 — Online engine và API

**Trạng thái: [x] Hoàn thành toàn bộ Giai đoạn 6 (6.1-6.4).**

### [x] 6.1 Tạo online engine

Tạo: `src/pit_feature_store/online_engine.py`

Hoàn thành khi có: `ingest_event()`, `compute_features()`, Redis ZSET, catalog-driven calculation.

### [x] 6.2 Tạo online replay

Tạo: `scripts/run_online_replay.py`

Hoàn thành khi: dọn Redis cũ, replay đúng thứ tự, compute trước ingest, có virtual clock.

### [x] 6.3 Tạo serving API

Tạo: `src/pit_feature_store/serving.py` (FastAPI app object), `scripts/run_api.py` (chạy uvicorn)

Hoàn thành khi: có endpoint `/features/{uid}`, trả đủ bốn feature, hỗ trợ `as_of_epoch`, trả 503 khi thiếu virtual clock.

### [x] 6.4 Test online engine và API

Tạo: `tests/unit/test_online_engine.py` (dùng `fakeredis`, không cần Redis thật), `tests/integration/test_serving_api.py` (FastAPI `TestClient` + `fakeredis`)

Hoàn thành khi test pass. Thêm `fakeredis`, `httpx` vào `requirements.txt` nếu chưa có.

---

## Giai đoạn 7 — Parity

**Trạng thái: [x] Hoàn thành toàn bộ Giai đoạn 7 (7.1-7.2).**

### [x] 7.1 Tạo parity script

Tạo: `src/pit_feature_store/parity.py` (logic), `scripts/run_parity.py` (CLI)

Hoàn thành khi: kiểm tra ≥50 mẫu, so đủ bốn feature, chuẩn hoá missing values, in thông tin mismatch nếu có.

### [x] 7.2 Tạo parity pytest

Tạo: `tests/integration/test_parity.py`

Hoàn thành khi: mismatch bằng 0, test pass.

---

## Giai đoạn 8 — Monitoring

### [ ] 8.1 Freshness monitoring

Tạo hoặc hoàn thiện: `src/pit_feature_store/monitoring/freshness.py`, `scripts/run_monitoring.py`

Hoàn thành khi: dùng virtual clock, không dùng giờ máy thật, in tuổi dữ liệu hợp lý.

### [ ] 8.2 PSI monitoring

Tạo hoặc hoàn thiện: `src/pit_feature_store/monitoring/psi.py`

Hoàn thành khi: tính được một giá trị PSI, có xử lý trường hợp phân phối rỗng hoặc bin bằng 0.

---

## Giai đoạn 9 — Tài liệu và báo cáo

### [ ] 9.1 Hoàn thiện proposal

Hoàn thành khi: đủ năm phần, vừa một trang A4.

### [ ] 9.2 Hoàn thiện system design

Hoàn thành khi: kiến trúc khớp source code thực tế (cấu trúc mới sau Giai đoạn 4.5), có time semantics, schema, parity mechanism.

### [ ] 9.3 Hoàn thiện báo cáo kết quả

Phải có: bảng ROC-AUC/PR-AUC, kết quả backfill idempotency, kết quả backfill/full-pipeline comparison, kết quả parity, hạn chế pseudo-entity.

---

## Giai đoạn 10 — Hoàn thiện dự án

### [ ] 10.1 Chạy toàn bộ test

Lệnh: `python -m pytest tests -v`

Hoàn thành khi: 0 failed, 0 error — cả `tests/unit` và `tests/integration`.

### [ ] 10.2 Kiểm tra README

Hoàn thành khi: có thể chạy dự án từ môi trường mới (bao gồm bước `pip install -e .`); các lệnh khớp source code thật theo cấu trúc mới.

Ghi chú 2026-08-11: README đã được chuẩn hóa cho workflow notebook EDA → warehouse
→ offline PIT → notebook model research; đã chạy 38 unit test và 41 test toàn bộ
sau khi bỏ hai test model/report không còn thuộc trách nhiệm của `leakage.py`.
Task vẫn để `[ ]` vì cần bổ sung/kiểm tra lại workflow online và parity sau khi
các giai đoạn 6-7 được triển khai.

Cập nhật 2026-08-14: README đã mô tả online replay, Redis virtual clock, serving
API, test Giai đoạn 6 và liên kết hướng dẫn Docker chi tiết. Task 10.2 vẫn để
`[ ]` vì parity Giai đoạn 7 và lượt xác minh toàn bộ tài liệu từ môi trường sạch
chưa được thực hiện.

Cập nhật sau Giai đoạn 7: parity đã được triển khai và test pass, nhưng task 10.2
vẫn để `[ ]` vì workflow parity chưa được bổ sung vào README và tài liệu chưa được
xác minh end-to-end từ môi trường sạch trong task có phạm vi riêng này.

### [ ] 10.3 Dọn repo

Hoàn thành khi:

- Không commit raw dataset, không commit `artifacts/` (toàn bộ), không commit `.env`, không có file tạm/cache.
- Xác nhận `evaluate_entity_candidates.py`/`leakage_experiment.py` bản `.py` cũ đã bị xoá khỏi root (đã thay bằng notebook + `src/`).

### [ ] 10.4 Chuẩn bị demo

Demo phải gồm: chạy backfill, gọi API, chạy parity test, hiển thị kết quả metric.
