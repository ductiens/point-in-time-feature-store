# AGENTS.md

## 1. Mục tiêu dự án

Xây dựng một Point-in-Time Correct Feature Store tối giản cho bộ dữ liệu
IEEE-CIS Fraud Detection.

Hệ thống phải chứng minh được:

1. Feature tại thời điểm training không sử dụng giao dịch hiện tại hoặc tương lai.
2. Offline engine và online engine cho cùng kết quả tại cùng `uid` và `cutoff`.
3. Backfill có thể chạy lại nhiều lần và tạo ra cùng dữ liệu.
4. Pipeline có thể chạy từ dữ liệu raw đến kết quả cuối.
5. Các kết quả quan trọng được kiểm chứng bằng test tự động.

## 2. Nguồn yêu cầu chính thức

Khi các file có nội dung mâu thuẫn, ưu tiên theo thứ tự:

1. `PROJECT_SPEC.md`: yêu cầu chính thức của dự án.
2. `TODO.md`: task và điều kiện hoàn thành.
3. Tests hiện tại.
4. Source code hiện tại.
5. `README.md`: hướng dẫn cài đặt và chạy.
6. `STATUS.md`: trạng thái gần nhất của dự án.

Không tự bổ sung yêu cầu ngoài phạm vi các file trên.

## 3. Quy trình trước khi sửa code

Trước mỗi task phải:

1. Đọc `PROJECT_SPEC.md`.
2. Đọc task tương ứng trong `TODO.md`.
3. Đọc `STATUS.md`.
4. Kiểm tra các file source liên quan.
5. Kiểm tra các test liên quan.
6. Chạy `git status`.
7. Trình bày kế hoạch ngắn trước khi sửa.

Không bắt đầu sửa code khi chưa xác định rõ:

- Mục tiêu task.
- File được phép thay đổi.
- Điều kiện hoàn thành.
- Lệnh kiểm tra cần chạy.

## 4. Quy tắc làm việc

- Chỉ thực hiện một task hoặc một nhóm task liên quan trực tiếp trong mỗi lần làm.
- Không tự chuyển sang task tiếp theo.
- Không tự mở rộng dự án sang Kafka, Spark, Feast, Airflow hoặc Kubernetes.
- Không xoá hoặc chỉnh sửa dữ liệu raw.
- Không ghi secret từ `.env` vào source code.
- Không commit `.env`, `.venv`, CSV Kaggle, DuckDB, Parquet hoặc Redis dump.
- Không sửa test chỉ để test pass.
- Khi sửa bug phải có regression test.
- Không ghi đè thay đổi chưa commit của người dùng.
- Không thay đổi kiến trúc ngoài phạm vi task.
- Không báo hoàn thành nếu chưa chạy lệnh kiểm tra thực tế.
- Giữ thay đổi nhỏ và tập trung đúng yêu cầu.

## 5. Quy tắc point-in-time bắt buộc

Mọi rolling feature sử dụng khoảng thời gian:

`[cutoff - window, cutoff)`

Điều đó có nghĩa:

- Bao gồm sự kiện tại đúng `cutoff - window`.
- Loại trừ sự kiện tại đúng `cutoff`.
- Một giao dịch không được sử dụng chính nó để tính feature của nó.
- Không được sử dụng bất kỳ giao dịch nào trong tương lai.

## 6. Quy tắc offline engine

- `label_spine` và `feature_events` phải là hai view tách biệt.
- `label_spine` chỉ chứa điểm cần dự đoán và label.
- `feature_events` chỉ chứa lịch sử sự kiện dùng để tính feature.
- Chỉ sử dụng event có `feature_ts < cutoff_ts`.
- Rolling feature phải đúng khi các giao dịch cách nhau nhiều ngày.
- Feature phải được sinh từ `feature_catalog.yaml`.
- Không hard-code lại tên feature hoặc window ở nhiều nơi nếu catalog đã chứa thông tin đó.

## 7. Quy tắc online engine

- Redis ZSET lưu raw events theo từng `uid`.
- Score của ZSET là timestamp epoch.
- Online engine phải tự tính feature từ raw events.
- Không copy feature đã tính từ DuckDB sang Redis.
- Khi replay một giao dịch:
  1. Tính feature tại timestamp của giao dịch.
  2. Sau đó mới ingest giao dịch hiện tại vào Redis.
- Event tại đúng cutoff phải bị loại trừ.

## 8. Quy tắc virtual clock

Dataset sử dụng timestamp giả lập bắt đầu từ năm 2017.

- Không sử dụng `time.time()` hoặc giờ thật của máy làm mặc định.
- Redis sử dụng key `sys:virtual_now_epoch`.
- Nếu API không nhận `as_of_epoch` và Redis chưa có virtual clock, API phải trả HTTP 503.
- Không được âm thầm trả feature bằng 0 khi hệ thống chưa sẵn sàng.

## 9. Quy tắc backfill

- Backfill phải tính lại từ bảng raw `transactions`.
- Backfill nhận `start_date` và `end_date`.
- Lookback phải bằng window lớn nhất trong catalog.
- Backfill phải sử dụng TEMP view/table để không ghi đè pipeline chính.
- Version output phải chứa fingerprint của catalog.
- Phải lưu snapshot của catalog cùng output.
- Phải ghi Parquet vào file tạm rồi replace file cuối.
- Chạy lại cùng input và cùng catalog phải cho cùng dữ liệu logic.
- Không so idempotency bằng byte hash của file Parquet; so dữ liệu sau khi đọc.

## 10. Quy tắc leakage experiment

- PIT và leaky dataset phải dùng cùng tên feature.
- PIT và leaky dataset phải dùng cùng độ dài window.
- PIT feature chỉ nhìn về quá khứ.
- Leaky feature nhìn về tương lai có chủ đích.
- Train/test split theo một mốc `cutoff_ts`.
- Không sử dụng random train/test split.
- Không cắt các giao dịch cùng timestamp sang hai tập khác nhau.
- Phải báo cáo cả ROC-AUC và PR-AUC.
- Không được giả định trước rằng metric leaky chắc chắn cao hơn; phải chạy thực nghiệm rồi phân tích kết quả.

## 11. Quy tắc test

Test phải bao phủ tối thiểu:

- Entity chưa có lịch sử.
- Giao dịch tại đúng cutoff.
- Giao dịch tại đúng biên dưới window.
- Khoảng trống lớn hơn 24 giờ.
- Khoảng trống lớn hơn 7 ngày.
- Khoảng trống lớn hơn 720 giờ.
- Hai entity khác nhau không bị trộn dữ liệu.
- Offline calculation khớp với tính tay bằng Pandas.
- Backfill idempotent.
- Offline và online parity.

Không yêu cầu full Kaggle dataset cho mọi unit test. Có thể tạo dữ liệu nhỏ trực tiếp trong test.

## 12. Definition of Done

Một task chỉ được đánh dấu hoàn thành khi:

1. Code đáp ứng điều kiện trong `TODO.md`.
2. Test liên quan đã được tạo hoặc cập nhật.
3. Test liên quan đã chạy và pass.
4. Không làm hỏng test cũ.
5. `TODO.md` được cập nhật trạng thái.
6. `STATUS.md` được cập nhật.
7. Codex báo rõ:
   - File đã thay đổi.
   - Nội dung chính đã làm.
   - Lệnh đã chạy.
   - Kết quả kiểm tra.
   - Hạn chế hoặc rủi ro còn lại.

Không ghi “test pass” nếu chưa thực sự chạy test.

## 13. Các lệnh cơ bản

Kích hoạt môi trường Windows PowerShell:

`.\.venv\Scripts\Activate.ps1`

Chạy toàn bộ test:

`python -m pytest tests -v`

Kiểm tra import:

`python -c "import duckdb, pandas, pyarrow, sklearn, lightgbm"`

Kiểm tra số dòng warehouse:

`python -c "import duckdb; con=duckdb.connect('warehouse.duckdb'); print(con.sql('SELECT COUNT(*) FROM transactions').fetchone()[0])"`

## 14. Mẫu báo cáo sau mỗi task

Codex phải trả lời theo cấu trúc:

### Đã thực hiện

### File đã thay đổi

### Lệnh đã chạy

### Kết quả kiểm tra

### Rủi ro hoặc hạn chế còn lại

### Task tiếp theo đề xuất

Không tự thực hiện task tiếp theo khi chưa được yêu cầu.